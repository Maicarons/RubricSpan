//! rubricspan-ocr —— 试卷作答文本识别（技术方案 §8 · M8.1 起纯 Rust 推理）。
//!
//! 处理链路：图像解码 → PP-OCR 文本检测（DB）→ 文本行识别（CTC）→ 阅读顺序排序
//! → 拼接作答文本 → 输出 [`rubricspan_core::ocr::OcrResult`]。
//!
//! 引擎：`rapidocr-core`（RapidOCR 官方 Rust 核心，内部以 `ort` 加载 ONNX，无 Python）。
//! 模型：模型目录下平铺 det/rec/cls 资产与字典；缺失时自动从 ModelScope 下载
//! （`sha256` 校验，见 `rapidocr_core::model::ModelDownloadMode::Missing`）。

use std::path::Path;
use std::sync::Mutex;

use rapidocr_core::config::{ExecutionProvider, InferenceOptions, PipelineConfig};
use rapidocr_core::model::{model_set_by_name, ModelCache, ModelDownloadMode};
use rapidocr_core::RapidOcr;
use rubricspan_core::ocr::{OcrLine, OcrResult};

/// OCR 引擎错误。
#[derive(Debug, thiserror::Error)]
pub enum OcrError {
    #[error("OCR 模型缺失：{0}")]
    ModelMissing(String),
    #[error("图像无法解析：{0}")]
    InvalidImage(String),
    #[error("识别失败：{0}")]
    Recognition(String),
}

/// 作答区坐标模板（题号 → 作答区区域）。
///
/// M8.1 先行实现全图识别；按模板作答区过滤（题号软切分）作为后续增强，
/// 当前 `recognize` 不按其过滤，仅保留契约类型。
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct AnswerRegionTemplate {
    pub template_id: String,
    /// 各题作答区区域：(题号, [x1, y1, x2, y2])。
    pub regions: Vec<(String, [f64; 4])>,
}

/// 低置信判定阈值：单行置信度低于该值标记为"识别存疑"。
pub const LOW_CONFIDENCE_THRESHOLD: f64 = 0.80;

/// 线程安全的 OCR 引擎（会话要求 `&mut self`，以互斥锁串行化）。
pub struct OcrEngine {
    ocr: Mutex<RapidOcr>,
}

impl OcrEngine {
    /// 打开 OCR 引擎：确保模型资产（缺失自动下载）并构建 det + rec 会话（无方向分类）。
    ///
    /// 推理执行提供器（EP）**优先 GPU（DirectML）**：`rapidocr-core` 仅暴露 Cpu / DirectMl
    /// 两个 EP（不透传 ort 的 CUDA），DirectML 走 Windows DirectX 12、不依赖 CUDA 运行库。
    /// `RUBRICSPAN_OCR_EP=cpu` 可强制 CPU（如 DirectX 12 不可用或需要完全确定性时）。
    ///
    /// 默认模型集 [`DEFAULT_MODEL_SET_NAME`]（ppocrv6-small，中英）；可用集见
    /// `rapidocr_core::model::model_set_by_name`（如 `ppocrv5-ch-mobile`）。
    pub fn open(model_dir: &Path, model_set: &str) -> Result<Self, OcrError> {
        let set = model_set_by_name(model_set)
            .ok_or_else(|| OcrError::ModelMissing(format!("未知模型集：{model_set}")))?;
        let cache = ModelCache::new(model_dir.to_path_buf());
        cache
            .ensure_model_set_for_pipeline(set, PipelineConfig::without_cls(), ModelDownloadMode::Missing)
            .map_err(|e| OcrError::ModelMissing(e.to_string()))?;
        // EP 选择：默认 DirectML（GPU）；RUBRICSPAN_OCR_EP=cpu 回落 CPU。
        let force_cpu = matches!(
            std::env::var("RUBRICSPAN_OCR_EP").as_deref(),
            Ok("cpu") | Ok("CPU")
        );
        let execution_provider = if force_cpu {
            ExecutionProvider::Cpu
        } else {
            ExecutionProvider::DirectMl
        };
        let cfg = cache
            .config_for(set)
            .with_pipeline(PipelineConfig::without_cls())
            .with_inference_options(InferenceOptions {
                intra_threads: 2,
                inter_threads: 1,
                // DirectML 要求关闭并行图执行（rapidocr-core fail-fast 校验）
                parallel_execution: false,
                enable_cpu_mem_arena: true,
                execution_provider,
            });
        let ocr = RapidOcr::from_config(cfg).map_err(|e| OcrError::Recognition(e.to_string()))?;
        tracing::info!(
            model_set,
            ep = ?execution_provider,
            dir = %model_dir.display(),
            "OCR 引擎就绪（det + rec）"
        );
        Ok(Self { ocr: Mutex::new(ocr) })
    }
}

/// 识别一张试卷图片，输出作答区文本。
///
/// `template` 暂参与全图识别（作答区过滤为后续增强）；`low_confidence` 在
/// 单行低于 [`LOW_CONFIDENCE_THRESHOLD`] 或整图无文本时置位（提示人工核对）。
pub fn recognize(
    engine: &OcrEngine,
    question_id: &str,
    image_bytes: &[u8],
    _template: Option<&AnswerRegionTemplate>,
) -> Result<OcrResult, OcrError> {
    let img = image::load_from_memory(image_bytes)
        .map_err(|e| OcrError::InvalidImage(e.to_string()))?
        .to_rgb8();

    let mut guard = engine
        .ocr
        .lock()
        .map_err(|e| OcrError::Recognition(e.to_string()))?;
    let output = guard
        .run_image(&img)
        .map_err(|e| OcrError::Recognition(e.to_string()))?;
    drop(guard);

    let mut lines: Vec<OcrLine> = output
        .lines
        .iter()
        .filter(|l| !l.text.trim().is_empty())
        .map(|l| OcrLine {
            text: l.text.trim().to_string(),
            r#box: Some(l.bbox.points.map(|p| [p[0] as f64, p[1] as f64]).to_vec()),
            score: l.score as f64,
            low_confidence: (l.score as f64) < LOW_CONFIDENCE_THRESHOLD,
        })
        .collect();
    sort_read_order(&mut lines);

    let answer_text = lines
        .iter()
        .map(|l| l.text.as_str())
        .collect::<Vec<_>>()
        .join("\n");
    let confidence: f64 = if lines.is_empty() {
        0.0
    } else {
        lines.iter().map(|l| l.score).sum::<f64>() / lines.len() as f64
    };
    let low_confidence = lines.is_empty() || lines.iter().any(|l| l.low_confidence);

    Ok(OcrResult {
        question_id: question_id.to_string(),
        answer_text,
        confidence,
        lines,
        low_confidence,
    })
}

/// 按阅读顺序排序：主键为检测框中心 y（上行优先），同 y 带内按 x 升序。
fn sort_read_order(lines: &mut [OcrLine]) {
    lines.sort_by(|a, b| {
        let ay = a
            .r#box
            .as_ref()
            .map(|b| b.iter().map(|p| p[1]).sum::<f64>() / b.len() as f64)
            .unwrap_or(0.0);
        let by = b
            .r#box
            .as_ref()
            .map(|b| b.iter().map(|p| p[1]).sum::<f64>() / b.len() as f64)
            .unwrap_or(0.0);
        ay.partial_cmp(&by)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| {
                let ax = a.r#box.as_ref().and_then(|b| b.first()).map(|p| p[0]).unwrap_or(0.0);
                let bx = b.r#box.as_ref().and_then(|b| b.first()).map(|p| p[0]).unwrap_or(0.0);
                ax.partial_cmp(&bx).unwrap_or(std::cmp::Ordering::Equal)
            })
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn mk_line(text: &str, y: f64, x: f64) -> OcrLine {
        OcrLine {
            text: text.into(),
            r#box: Some(vec![[x, y], [x + 40.0, y], [x + 40.0, y + 12.0], [x, y + 12.0]]),
            score: 0.95,
            low_confidence: false,
        }
    }

    #[test]
    fn read_order_sorts_by_y_then_x() {
        let mut lines = vec![mk_line("第二行", 90.0, 10.0), mk_line("第一行", 10.0, 30.0)];
        sort_read_order(&mut lines);
        assert_eq!(lines[0].text, "第一行");
        assert_eq!(lines[1].text, "第二行");
    }

    #[test]
    fn same_row_sorts_by_x() {
        let mut lines = vec![mk_line("右", 10.0, 60.0), mk_line("左", 10.0, 5.0)];
        sort_read_order(&mut lines);
        assert_eq!(lines[0].text, "左");
        assert_eq!(lines[1].text, "右");
    }
}