"use client";

import { useCallback, useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  listProjects, createProject, getProject, deleteProject,
  listQuestions, createQuestion, deleteQuestion,
  getStandardAnswer, parseStandardAnswer, saveStandardAnswer,
  listAnswers, submitAnswers, deleteAnswer,
  scoreAnswers, listResults,
  type Project, type Question, type Answer, type ScoreResult, type ScoreRecord,
  type ScoringConfig, type ScoringPoint, type ConfigStatus,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { Field, TextInput } from "@/components/ui/field";
import { Progress } from "@/components/ui/progress";
import {
  IconBook, IconCheck, IconRefresh, IconPlus, IconTrash2, IconAlert, IconX,
  IconArrowRight, IconPen, IconUsers, IconGrid, IconSliders,
} from "@/components/icons";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_LABEL: Record<ConfigStatus, string> = { none: "未配置", pending_review: "待审核", confirmed: "已确认" };
const STATUS_TONE: Record<ConfigStatus, "neutral" | "warn" | "ok"> = { none: "neutral", pending_review: "warn", confirmed: "ok" };
const RATING_LABEL: Record<string, string> = { excellent: "优秀", good: "良好", pass: "及格", fail: "不及格" };
const RATING_TONE: Record<string, "ok" | "info" | "warn" | "danger"> = { excellent: "ok", good: "info", pass: "warn", fail: "danger" };
const HIT_LABEL: Record<string, string> = { hit_exact: "精确命中", hit_semantic: "语义命中", partial: "部分命中", miss: "未命中" };
const HIT_TONE: Record<string, "ok" | "info" | "warn" | "neutral"> = { hit_exact: "ok", hit_semantic: "info", partial: "warn", miss: "neutral" };

// ---------------------------------------------------------------------------
// Main page — delegates to list or detail view based on ?id= query param
// ---------------------------------------------------------------------------

export default function AdminProjectsPage() {
  return (
    <Suspense fallback={<div className="mt-6 space-y-4" aria-hidden="true"><div className="h-8 w-64 animate-pulse rounded-lg bg-surface" /></div>}>
      <ProjectsPageInner />
    </Suspense>
  );
}

function ProjectsPageInner() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("id");

  if (projectId) {
    return <ProjectDetailPage projectId={projectId} />;
  }

  return <ProjectListPage />;
}

// ---------------------------------------------------------------------------
// List mode — show all projects as cards
// ---------------------------------------------------------------------------

function ProjectListPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newSubject, setNewSubject] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const res = await listProjects();
      setProjects(res.items);
    } catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function handleCreate() {
    if (!newName.trim()) return;
    setCreating(true); setErr(null);
    try {
      await createProject({
        name: newName.trim(),
        description: newDesc.trim() || undefined,
        subject: newSubject.trim() || undefined,
      });
      setShowCreate(false);
      setNewName(""); setNewDesc(""); setNewSubject("");
      void load();
    } catch (e) { setErr(String(e)); }
    finally { setCreating(false); }
  }

  async function handleDelete(id: string) {
    if (!window.confirm("确定要删除这个工程吗？工程下的所有试题、答卷和评分记录将一并删除。")) return;
    try {
      await deleteProject(id);
      void load();
    } catch (e) { setErr(String(e)); }
  }

  return (
    <>
      <PageHeader title="工程项目" desc="创建和管理阅卷工程。每个工程可包含多道试题、答卷和评分记录。"
        action={<Button onClick={() => setShowCreate(true)} icon={<IconPlus className="h-4 w-4" />}>新建工程</Button>} />

      {err && !loading && (
        <div role="alert" className="mt-4 rounded-lg border border-danger/40 bg-danger-soft px-3.5 py-3 text-sm leading-relaxed text-danger">{err}</div>
      )}

      {/* 新建工程对话框 */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-lg animate-scale-in rounded-xl border border-line bg-surface p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-serif text-lg font-semibold text-ink">新建工程</h2>
              <button onClick={() => setShowCreate(false)} className="rounded-lg p-1.5 text-ink-3 hover:bg-surface-2 hover:text-ink">
                <IconX className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <Field label="工程名称">
                <TextInput value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="如：2024 学年期中考试" />
              </Field>
              <Field label="科目（可选）">
                <TextInput value={newSubject} onChange={(e) => setNewSubject(e.target.value)} placeholder="如：语文" />
              </Field>
              <Field label="描述（可选）">
                <textarea value={newDesc} onChange={(e) => setNewDesc(e.target.value)} rows={3}
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 transition-colors focus:border-accent focus:outline-none focus:ring ring-accent/15" placeholder="工程描述（可选）" />
              </Field>
            </div>
            <div className="mt-6 flex items-center justify-end gap-2">
              <Button onClick={() => setShowCreate(false)}>取消</Button>
              <Button variant="primary" onClick={handleCreate} disabled={creating || !newName.trim()} loading={creating}>创建</Button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="mt-6 space-y-3" aria-hidden="true">
          {[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-xl border border-line bg-surface" />)}
        </div>
      ) : (
        <div className="mt-6 space-y-3">
          {projects.length === 0 ? (
            <Card className="p-8 text-center">
              <p className="text-sm text-ink-3">暂无工程项目，点击「新建工程」创建。</p>
            </Card>
          ) : (
            projects.map((p) => (
              <Card key={p.project_id} className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <Link href={`/projects?id=${encodeURIComponent(p.project_id)}`} className="min-w-0 flex-1 group">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-ink group-hover:text-accent transition-colors">{p.name}</span>
                      <Badge tone={p.status === "active" ? "ok" : "neutral"}>{p.status === "active" ? "进行中" : p.status}</Badge>
                    </div>
                    {p.description && <p className="mt-1 text-sm text-ink-2">{p.description}</p>}
                    <div className="mt-2 flex items-center gap-3 text-xs text-ink-3">
                      {p.subject && <span>科目：{p.subject}</span>}
                      <span>创建于：{new Date(p.created_at).toLocaleDateString("zh-CN")}</span>
                    </div>
                  </Link>
                  <div className="flex shrink-0 items-center gap-2">
                    <Link href={`/projects?id=${encodeURIComponent(p.project_id)}`}>
                      <Button size="sm" icon={<IconArrowRight className="h-3.5 w-3.5" />}>进入</Button>
                    </Link>
                    <Button size="sm" variant="danger" onClick={() => handleDelete(p.project_id)} icon={<IconTrash2 className="h-3.5 w-3.5" />}>删除</Button>
                  </div>
                </div>
              </Card>
            ))
          )}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Detail mode — project workspace with tabs
// ---------------------------------------------------------------------------

type TabId = "questions" | "answers" | "scoring";

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "questions", label: "试题", icon: <IconBook className="h-4 w-4" /> },
  { id: "answers", label: "答卷", icon: <IconUsers className="h-4 w-4" /> },
  { id: "scoring", label: "评分", icon: <IconPen className="h-4 w-4" /> },
];

function ProjectDetailPage({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("questions");

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const p = await getProject(projectId);
      setProject(p);
    } catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { void load(); }, [load]);

  if (loading) {
    return (
      <div className="space-y-4" aria-hidden="true">
        <div className="h-8 w-64 animate-pulse rounded-lg bg-surface" />
        <div className="h-12 animate-pulse rounded-lg bg-surface" />
        <div className="h-64 animate-pulse rounded-xl border border-line bg-surface" />
      </div>
    );
  }

  if (err || !project) {
    return (
      <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft px-3.5 py-3 text-sm leading-relaxed text-danger">
        {err || "工程未找到"}
        <p className="mt-1"><Link href="/projects" className="underline">返回工程列表</Link></p>
      </div>
    );
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <Link href="/projects" className="inline-flex items-center gap-1 text-xs text-ink-3 hover:text-accent transition-colors">
            <IconArrowRight className="h-3.5 w-3.5 rotate-180" />返回工程列表
          </Link>
          <h1 className="mt-1 font-serif text-2xl font-bold tracking-wide text-ink">{project.name}</h1>
          <div className="mt-1 flex items-center gap-3 text-sm text-ink-3">
            {project.subject && <span>科目：{project.subject}</span>}
            <Badge tone={project.status === "active" ? "ok" : "neutral"}>{project.status === "active" ? "进行中" : project.status}</Badge>
            <span>创建于：{new Date(project.created_at).toLocaleDateString("zh-CN")}</span>
          </div>
          {project.description && <p className="mt-1.5 text-sm text-ink-2">{project.description}</p>}
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 border-b border-line" role="tablist">
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button key={tab.id} role="tab" aria-selected={active} onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
                active ? "border-accent text-accent" : "border-transparent text-ink-3 hover:text-ink hover:border-line-strong"
              }`}>
              {tab.icon} {tab.label}
            </button>
          );
        })}
      </div>

      {activeTab === "questions" && <QuestionsTab projectId={projectId} />}
      {activeTab === "answers" && <AnswersTab projectId={projectId} />}
      {activeTab === "scoring" && <ScoringTab projectId={projectId} />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Questions Tab
// ---------------------------------------------------------------------------

function QuestionsTab({ projectId }: { projectId: string }) {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [newSubject, setNewSubject] = useState("");
  const [newTotalScore, setNewTotalScore] = useState(10);
  const [newStdAnswer, setNewStdAnswer] = useState("");

  // Standard answer editor
  const [editingQid, setEditingQid] = useState<string | null>(null);
  const [scoringConfig, setScoringConfig] = useState<ScoringConfig | null>(null);
  const [rawAnswerText, setRawAnswerText] = useState("");
  const [parseWarnings, setParseWarnings] = useState<string[]>([]);
  const [savingStd, setSavingStd] = useState(false);
  const [stdMsg, setStdMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const res = await listQuestions();
      // Filter by project if the backend supports it; otherwise filter client-side
      const items = res.items.filter((q) => q.project_id === projectId);
      setQuestions(items);
    } catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { void load(); }, [load]);

  async function handleCreate() {
    if (!newContent.trim() || !newSubject.trim()) return;
    setCreating(true); setErr(null);
    try {
      await createQuestion({
        content: newContent.trim(),
        subject: newSubject.trim(),
        total_score: newTotalScore,
        standard_answer_text: newStdAnswer.trim() || undefined,
        project_id: projectId,
      });
      setShowCreate(false);
      setNewContent(""); setNewSubject(""); setNewTotalScore(10); setNewStdAnswer("");
      void load();
    } catch (e) { setErr(String(e)); }
    finally { setCreating(false); }
  }

  async function handleDelete(id: string) {
    if (!window.confirm("确定要删除这道试题吗？相关答卷和评分记录不会被自动删除。")) return;
    try {
      await deleteQuestion(id);
      void load();
    } catch (e) { setErr(String(e)); }
  }

  async function openStdEditor(q: Question) {
    setEditingQid(q.question_id);
    setRawAnswerText(q.standard_answer_text ?? "");
    setParseWarnings([]);
    setStdMsg(null);
    try {
      const cfg = await getStandardAnswer(q.question_id);
      setScoringConfig(cfg);
    } catch {
      setScoringConfig(null);
    }
  }

  async function handleParse() {
    if (!editingQid) return;
    setStdMsg(null);
    try {
      const q = questions.find((x) => x.question_id === editingQid);
      const result = await parseStandardAnswer(editingQid, rawAnswerText, q?.content);
      setScoringConfig(result.scoring_config);
      setParseWarnings(result.warnings);
    } catch (e) {
      setStdMsg({ tone: "danger", text: `解析失败：${e instanceof Error ? e.message : String(e)}` });
    }
  }

  async function handleSaveStd() {
    if (!scoringConfig) return;
    setSavingStd(true); setStdMsg(null);
    try {
      await saveStandardAnswer(scoringConfig);
      setStdMsg({ tone: "ok", text: "已保存" });
      void load();
    } catch (e) { setStdMsg({ tone: "danger", text: `保存失败：${e instanceof Error ? e.message : String(e)}` }); }
    finally { setSavingStd(false); }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-3">管理本项目下的试题及其标准答案配置。</p>
        <Button onClick={() => setShowCreate(true)} icon={<IconPlus className="h-4 w-4" />}>新建试题</Button>
      </div>

      {err && (
        <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft px-3.5 py-3 text-sm leading-relaxed text-danger">{err}</div>
      )}

      {/* 新建试题对话框 */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-lg animate-scale-in rounded-xl border border-line bg-surface p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-serif text-lg font-semibold text-ink">新建试题</h2>
              <button onClick={() => setShowCreate(false)} className="rounded-lg p-1.5 text-ink-3 hover:bg-surface-2 hover:text-ink">
                <IconX className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <Field label="题目内容">
                <textarea value={newContent} onChange={(e) => setNewContent(e.target.value)} rows={3}
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 transition-colors focus:border-accent focus:outline-none focus:ring ring-accent/15" placeholder="输入试题内容" />
              </Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="科目">
                  <TextInput value={newSubject} onChange={(e) => setNewSubject(e.target.value)} placeholder="如：语文" />
                </Field>
                <Field label="满分">
                  <TextInput type="number" min={1} value={newTotalScore} onChange={(e) => setNewTotalScore(Number(e.target.value))} />
                </Field>
              </div>
              <Field label="参考答案（可选）" hint="填入后可在下一步自动解析得分点">
                <textarea value={newStdAnswer} onChange={(e) => setNewStdAnswer(e.target.value)} rows={3}
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 transition-colors focus:border-accent focus:outline-none focus:ring ring-accent/15" placeholder="参考答案文本（可选）" />
              </Field>
            </div>
            <div className="mt-6 flex items-center justify-end gap-2">
              <Button onClick={() => setShowCreate(false)}>取消</Button>
              <Button variant="primary" onClick={handleCreate} disabled={creating || !newContent.trim() || !newSubject.trim()} loading={creating}>创建</Button>
            </div>
          </div>
        </div>
      )}

      {/* 标准答案配置对话框 */}
      {editingQid && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={() => setEditingQid(null)}>
          <div className="max-h-[85vh] w-full max-w-2xl animate-scale-in overflow-y-auto rounded-xl border border-line bg-surface p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-serif text-lg font-semibold text-ink">标准答案配置 · {editingQid}</h2>
              <button onClick={() => setEditingQid(null)} className="rounded-lg p-1.5 text-ink-3 hover:bg-surface-2 hover:text-ink">
                <IconX className="h-5 w-5" />
              </button>
            </div>

            <Field label="参考答案文本" hint="支持 Markdown 格式，可含得分点标记">
              <textarea value={rawAnswerText} onChange={(e) => setRawAnswerText(e.target.value)} rows={4}
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 transition-colors focus:border-accent focus:outline-none focus:ring ring-accent/15" placeholder="填入参考答案文本，点击「解析得分点」自动提取" />
            </Field>
            <div className="mt-3 flex items-center gap-2">
              <Button variant="primary" onClick={handleParse} icon={<IconRefresh className="h-4 w-4" />}>解析得分点</Button>
            </div>

            {parseWarnings.length > 0 && (
              <div className="mt-3 space-y-1">
                {parseWarnings.map((w, i) => (
                  <p key={i} className="flex items-start gap-1.5 text-xs text-warn"><IconAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />{w}</p>
                ))}
              </div>
            )}

            {scoringConfig && (
              <div className="mt-4 space-y-4">
                <div className="rounded-lg border border-line bg-surface-2 px-4 py-3">
                  <div className="flex items-center gap-4 text-sm">
                    <span className="text-ink-3">满分：<span className="font-mono text-ink">{scoringConfig.total_score}</span></span>
                    <span className="text-ink-3">得分点：<span className="font-mono text-ink">{scoringConfig.points.length}</span></span>
                    {scoringConfig.thresholds && (
                      <span className="text-ink-3">阈值：<span className="font-mono text-ink-2">{scoringConfig.thresholds.similarity_high} / {scoringConfig.thresholds.similarity_low}</span></span>
                    )}
                  </div>
                </div>

                <div className="space-y-3">
                  {scoringConfig.points.map((pt, idx) => (
                    <PointEditor key={pt.point_id} point={pt} index={idx}
                      onChange={(updated) => {
                        const pts = [...scoringConfig.points];
                        pts[idx] = updated;
                        setScoringConfig({ ...scoringConfig, points: pts });
                      }}
                      onDelete={() => {
                        const pts = scoringConfig.points.filter((_, i) => i !== idx);
                        setScoringConfig({ ...scoringConfig, points: pts });
                      }} />
                  ))}
                </div>

                <Button variant="secondary" icon={<IconPlus className="h-4 w-4" />} onClick={() => {
                  const maxId = Math.max(0, ...scoringConfig.points.map((p) => p.point_id));
                  setScoringConfig({
                    ...scoringConfig,
                    points: [...scoringConfig.points, { point_id: maxId + 1, point_text: "", weight: 1, aliases: [] }],
                  });
                }}>添加得分点</Button>

                {stdMsg && (
                  <div className={`mt-2 rounded-lg px-3.5 py-2.5 text-sm ${stdMsg.tone === "ok" ? "bg-ok-soft text-ok" : "bg-danger-soft text-danger"}`}>
                    {stdMsg.text}
                  </div>
                )}

                <div className="flex items-center gap-2">
                  <Button variant="primary" onClick={handleSaveStd} disabled={savingStd} loading={savingStd} icon={<IconCheck className="h-4 w-4" />}>保存配置</Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {loading ? (
        <div className="space-y-3" aria-hidden="true">
          {[0, 1, 2].map((i) => <div key={i} className="h-20 animate-pulse rounded-xl border border-line bg-surface" />)}
        </div>
      ) : (
        <div className="space-y-3">
          {questions.length === 0 ? (
            <Card className="p-8 text-center">
              <p className="text-sm text-ink-3">本项目暂无试题，点击「新建试题」添加。</p>
            </Card>
          ) : (
            questions.map((q) => (
              <Card key={q.question_id} className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-ink-3">{q.question_id}</span>
                      <Badge tone={STATUS_TONE[q.config_status]}>{STATUS_LABEL[q.config_status]}</Badge>
                    </div>
                    <p className="mt-1.5 text-sm leading-relaxed text-ink">{q.content}</p>
                    <div className="mt-2 flex items-center gap-3 text-xs text-ink-3">
                      <span>科目：{q.subject}</span>
                      <span>满分：{q.total_score}</span>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button size="sm" onClick={() => openStdEditor(q)}>配置标准答案</Button>
                    <Button size="sm" variant="danger" onClick={() => handleDelete(q.question_id)} icon={<IconTrash2 className="h-3.5 w-3.5" />}>删除</Button>
                  </div>
                </div>
              </Card>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Answers Tab
// ---------------------------------------------------------------------------

function AnswersTab({ projectId }: { projectId: string }) {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [selectedQid, setSelectedQid] = useState<string>("");
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showSubmit, setShowSubmit] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitRows, setSubmitRows] = useState<{ student_id: string; class_name: string; answer_text: string }[]>([
    { student_id: "", class_name: "", answer_text: "" },
  ]);

  useEffect(() => {
    listQuestions().then((res) => {
      const items = res.items.filter((q) => q.project_id === projectId);
      setQuestions(items);
    }).catch(() => {});
  }, [projectId]);

  const loadAnswers = useCallback(async (qid: string) => {
    if (!qid) { setAnswers([]); return; }
    setLoading(true); setErr(null);
    try {
      const res = await listAnswers(qid);
      setAnswers(res.items);
    } catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (selectedQid) void loadAnswers(selectedQid);
    else setAnswers([]);
  }, [selectedQid, loadAnswers]);

  async function handleSubmit() {
    const valid = submitRows.filter((r) => r.answer_text.trim());
    if (valid.length === 0) return;
    setSubmitting(true); setErr(null);
    try {
      await submitAnswers({
        question_id: selectedQid,
        submissions: valid.map((r) => ({
          student_id: r.student_id.trim() || undefined,
          class_name: r.class_name.trim() || undefined,
          answer_text: r.answer_text.trim(),
        })),
      });
      setShowSubmit(false);
      setSubmitRows([{ student_id: "", class_name: "", answer_text: "" }]);
      void loadAnswers(selectedQid);
    } catch (e) { setErr(String(e)); }
    finally { setSubmitting(false); }
  }

  async function handleDelete(id: string) {
    if (!window.confirm("确定要删除这份答卷吗？")) return;
    try {
      await deleteAnswer(id);
      void loadAnswers(selectedQid);
    } catch (e) { setErr(String(e)); }
  }

  function addRow() {
    setSubmitRows([...submitRows, { student_id: "", class_name: "", answer_text: "" }]);
  }

  function updateRow(i: number, field: keyof (typeof submitRows)[0], value: string) {
    const rows = [...submitRows];
    rows[i] = { ...rows[i], [field]: value };
    setSubmitRows(rows);
  }

  function removeRow(i: number) {
    if (submitRows.length <= 1) return;
    setSubmitRows(submitRows.filter((_, j) => j !== i));
  }

  const selectedQuestion = questions.find((q) => q.question_id === selectedQid);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="选择试题" className="min-w-60 flex-1">
          <select value={selectedQid} onChange={(e) => setSelectedQid(e.target.value)}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink transition-colors focus:border-accent focus:outline-none focus:ring ring-accent/15">
            <option value="">— 请选择试题 —</option>
            {questions.map((q) => (
              <option key={q.question_id} value={q.question_id}>{q.question_id} · {q.content.slice(0, 50)}{q.content.length > 50 ? "…" : ""}</option>
            ))}
          </select>
        </Field>
        {selectedQid && (
          <Button variant="primary" onClick={() => setShowSubmit(true)} icon={<IconPlus className="h-4 w-4" />}>新建答卷</Button>
        )}
      </div>

      {err && (
        <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft px-3.5 py-3 text-sm leading-relaxed text-danger">{err}</div>
      )}

      {selectedQid && (
        <Card className="p-5">
          <CardHeader title={`答卷列表`}
            desc={selectedQuestion ? `科目：${selectedQuestion.subject} · 满分：${selectedQuestion.total_score}` : undefined}
            action={<Button size="sm" onClick={() => loadAnswers(selectedQid)} icon={<IconRefresh className="h-3.5 w-3.5" />}>刷新</Button>} />

          {loading ? (
            <div className="mt-4 space-y-3" aria-hidden="true">
              {[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse rounded-lg border border-line bg-surface" />)}
            </div>
          ) : answers.length === 0 ? (
            <p className="mt-4 text-sm text-ink-3">暂无答卷，点击「新建答卷」添加。</p>
          ) : (
            <div className="mt-4 space-y-2.5">
              {answers.map((a) => (
                <div key={a.answer_id} className="flex items-start justify-between gap-3 rounded-lg border border-line bg-surface-2 p-3.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-xs text-ink-3">
                      <span className="font-mono">{a.answer_id}</span>
                      {a.student_id && <span>学号：{a.student_id}</span>}
                      {a.class_name && <span>班级：{a.class_name}</span>}
                      {a.source && <Badge tone="neutral">{a.source}</Badge>}
                    </div>
                    {a.answer_text && <p className="mt-1.5 text-sm text-ink">{a.answer_text}</p>}
                    {a.ocr_text && <p className="mt-1 text-xs text-ink-3">OCR：{a.ocr_text}</p>}
                  </div>
                  <Button size="sm" variant="danger" onClick={() => handleDelete(a.answer_id)} icon={<IconTrash2 className="h-3.5 w-3.5" />}>删除</Button>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* 批量提交答卷对话框 */}
      {showSubmit && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={() => setShowSubmit(false)}>
          <div className="max-h-[80vh] w-full max-w-2xl animate-scale-in overflow-y-auto rounded-xl border border-line bg-surface p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-serif text-lg font-semibold text-ink">批量提交答卷 · {selectedQid}</h2>
              <button onClick={() => setShowSubmit(false)} className="rounded-lg p-1.5 text-ink-3 hover:bg-surface-2 hover:text-ink">
                <IconX className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-4">
              {submitRows.map((row, i) => (
                <div key={i} className="rounded-lg border border-line bg-surface-2 p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-medium text-ink-3">答卷 #{i + 1}</span>
                    {submitRows.length > 1 && (
                      <button onClick={() => removeRow(i)} className="text-xs text-danger hover:underline">移除</button>
                    )}
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="学号（可选）">
                      <TextInput value={row.student_id} onChange={(e) => updateRow(i, "student_id", e.target.value)} placeholder="如：2024001" />
                    </Field>
                    <Field label="班级（可选）">
                      <TextInput value={row.class_name} onChange={(e) => updateRow(i, "class_name", e.target.value)} placeholder="如：高一(1)班" />
                    </Field>
                  </div>
                  <Field label="答卷内容" className="mt-3">
                    <textarea value={row.answer_text} onChange={(e) => updateRow(i, "answer_text", e.target.value)} rows={3}
                      className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 transition-colors focus:border-accent focus:outline-none focus:ring ring-accent/15" placeholder="输入学生答案" />
                  </Field>
                </div>
              ))}
            </div>

            <div className="mt-4 flex items-center gap-2">
              <Button onClick={addRow} icon={<IconPlus className="h-4 w-4" />}>添加一行</Button>
            </div>

            <div className="mt-6 flex items-center justify-end gap-2">
              <Button onClick={() => setShowSubmit(false)}>取消</Button>
              <Button variant="primary" onClick={handleSubmit} disabled={submitting || submitRows.every((r) => !r.answer_text.trim())} loading={submitting}>
                提交 {submitRows.filter((r) => r.answer_text.trim()).length} 份答卷
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scoring Tab
// ---------------------------------------------------------------------------

function ScoringTab({ projectId }: { projectId: string }) {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [selectedQid, setSelectedQid] = useState<string>("");
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [selectedAids, setSelectedAids] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [scoring, setScoring] = useState(false);
  const [results, setResults] = useState<ScoreResult[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showResults, setShowResults] = useState(false);

  useEffect(() => {
    listQuestions().then((res) => {
      const items = res.items.filter((q) => q.project_id === projectId);
      setQuestions(items);
    }).catch(() => {});
  }, [projectId]);

  const loadAnswers = useCallback(async (qid: string) => {
    if (!qid) { setAnswers([]); return; }
    setLoading(true);
    try {
      const res = await listAnswers(qid);
      setAnswers(res.items);
    } catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (selectedQid) {
      void loadAnswers(selectedQid);
      setSelectedAids(new Set());
      setResults(null);
      setShowResults(false);
    } else {
      setAnswers([]);
    }
  }, [selectedQid, loadAnswers]);

  function toggleAnswer(id: string) {
    setSelectedAids((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    if (selectedAids.size === answers.length) {
      setSelectedAids(new Set());
    } else {
      setSelectedAids(new Set(answers.map((a) => a.answer_id)));
    }
  }

  async function handleScore() {
    if (selectedAids.size === 0) return;
    setScoring(true); setErr(null); setResults(null);
    try {
      const res = await scoreAnswers(selectedQid, [...selectedAids]);
      setResults(res.results);
      setShowResults(true);
    } catch (e) { setErr(String(e)); }
    finally { setScoring(false); }
  }

  const selectedQuestion = questions.find((q) => q.question_id === selectedQid);

  return (
    <div className="space-y-4">
      <div className="max-w-lg">
        <Field label="选择试题" hint="切换试题将清空已选答卷和评分结果。">
          <select value={selectedQid} onChange={(e) => setSelectedQid(e.target.value)}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink transition-colors focus:border-accent focus:outline-none focus:ring ring-accent/15">
            <option value="">— 请选择试题 —</option>
            {questions.map((q) => (
              <option key={q.question_id} value={q.question_id}>{q.question_id} · {q.content.slice(0, 60)}{q.content.length > 60 ? "…" : ""}</option>
            ))}
          </select>
        </Field>
      </div>

      {err && (
        <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft px-3.5 py-3 text-sm leading-relaxed text-danger">{err}</div>
      )}

      {selectedQid && (
        <Card className="p-5">
          <CardHeader title="勾选答卷"
            desc={selectedQuestion ? `科目：${selectedQuestion.subject} · 满分：${selectedQuestion.total_score}` : undefined}
            action={
              <div className="flex items-center gap-2">
                <Button size="sm" onClick={selectAll} icon={<IconCheck className="h-3.5 w-3.5" />}>
                  {selectedAids.size === answers.length ? "取消全选" : "全选"}
                </Button>
                <Button size="sm" onClick={() => loadAnswers(selectedQid)} icon={<IconRefresh className="h-3.5 w-3.5" />}>刷新</Button>
              </div>
            } />

          {loading ? (
            <div className="mt-4 space-y-3" aria-hidden="true">
              {[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse rounded-lg border border-line bg-surface" />)}
            </div>
          ) : answers.length === 0 ? (
            <p className="mt-4 text-sm text-ink-3">暂无答卷，请先到「答卷」标签页添加。</p>
          ) : (
            <div className="mt-4 space-y-2">
              {answers.map((a) => {
                const checked = selectedAids.has(a.answer_id);
                return (
                  <label key={a.answer_id}
                    className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3.5 transition-colors ${
                      checked ? "border-accent bg-accent-soft" : "border-line bg-surface-2 hover:border-line-strong"
                    }`}>
                    <input type="checkbox" checked={checked} onChange={() => toggleAnswer(a.answer_id)}
                      className="mt-1 h-4 w-4 shrink-0 accent-accent" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 text-xs text-ink-3">
                        <span className="font-mono">{a.answer_id}</span>
                        {a.student_id && <span>学号：{a.student_id}</span>}
                        {a.class_name && <span>班级：{a.class_name}</span>}
                      </div>
                      {a.answer_text && <p className="mt-1 text-sm text-ink">{a.answer_text}</p>}
                      {a.ocr_text && <p className="mt-1 text-xs text-ink-3">OCR：{a.ocr_text}</p>}
                    </div>
                  </label>
                );
              })}
            </div>
          )}

          <div className="mt-4 flex items-center gap-2">
            <Button variant="primary" onClick={handleScore} disabled={scoring || selectedAids.size === 0} loading={scoring} icon={<IconPen className="h-4 w-4" />}>
              执行评分（{selectedAids.size} 份）
            </Button>
            {selectedAids.size > 0 && (
              <span className="text-xs text-ink-3">已选 {selectedAids.size} / {answers.length} 份答卷</span>
            )}
          </div>
        </Card>
      )}

      {showResults && results && (
        <Card className="p-5">
          <CardHeader title="评分结果" desc={`共 ${results.length} 份答卷评分完成`}
            action={<Badge tone="ok" dot>评分完成</Badge>} />

          <div className="mt-4 space-y-4">
            {results.map((r) => {
              const pct = r.max_score > 0 ? (r.total_score / r.max_score) * 100 : 0;
              return (
                <div key={r.answer_id} className="rounded-lg border border-line bg-surface-2 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-ink-3">{r.answer_id}</span>
                        {r.student_id && <span className="text-xs text-ink-3">学号：{r.student_id}</span>}
                        {r.class_name && <span className="text-xs text-ink-3">班级：{r.class_name}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-serif text-xl font-bold text-ink">{r.total_score}</span>
                      <span className="text-sm text-ink-3">/ {r.max_score}</span>
                      <Badge tone={RATING_TONE[r.rating]}>{RATING_LABEL[r.rating]}</Badge>
                    </div>
                  </div>
                  <Progress className="mt-2" value={pct} tone={RATING_TONE[r.rating]} />
                  {r.ocr_confidence != null && (
                    <p className="mt-2 text-xs text-ink-3">OCR 置信度：{(r.ocr_confidence * 100).toFixed(0)}%</p>
                  )}
                  {r.point_details.length > 0 && (
                    <div className="mt-3 space-y-1.5">
                      {r.point_details.map((pd) => (
                        <div key={pd.point_id} className="flex items-start gap-2 rounded-md bg-surface px-3 py-2 text-xs">
                          <Badge tone={HIT_TONE[pd.hit_status]}>{HIT_LABEL[pd.hit_status]}</Badge>
                          <span className="text-ink-2">得分点 #{pd.point_id}</span>
                          <span className="text-ink-3">得分：{pd.point_score}</span>
                          {pd.similarity != null && <span className="text-ink-3">相似度：{pd.similarity.toFixed(3)}</span>}
                          {pd.extracted_span && <span className="text-ink-3">抽取："{pd.extracted_span}"</span>}
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="mt-2 text-[10px] text-ink-3">评分时间：{r.scored_at}</p>
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PointEditor (shared component for standard answer editing)
// ---------------------------------------------------------------------------

function PointEditor({ point, index, onChange, onDelete }: {
  point: ScoringPoint; index: number; onChange: (p: ScoringPoint) => void; onDelete: () => void;
}) {
  const [aliasInput, setAliasInput] = useState("");
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-xs font-medium text-accent">得分点 #{index + 1} (ID: {point.point_id})</span>
        <Button size="sm" variant="ghost" onClick={onDelete} icon={<IconX className="h-3.5 w-3.5" />}>删除</Button>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Field label="得分点描述">
          <TextInput value={point.point_text} onChange={(e) => onChange({ ...point, point_text: e.target.value })} placeholder={'如：答出"因为"并合理解释'} />
        </Field>
        <Field label="权重">
          <TextInput type="number" step={0.5} min={0} value={point.weight} onChange={(e) => onChange({ ...point, weight: Number(e.target.value) })} />
        </Field>
      </div>
      <Field label="同义表达（别名）" className="mt-3" hint="每行一个，如：因为、由于、之所以">
        <div className="flex flex-wrap gap-1.5">
          {point.aliases.map((a, i) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-md bg-surface-2 px-2 py-1 text-xs text-ink-2">
              {a}
              <button onClick={() => onChange({ ...point, aliases: point.aliases.filter((_, j) => j !== i) })}
                className="text-ink-3 hover:text-danger"><IconX className="h-3 w-3" /></button>
            </span>
          ))}
        </div>
        <div className="mt-2 flex gap-2">
          <TextInput value={aliasInput} onChange={(e) => setAliasInput(e.target.value)} placeholder="添加别名" className="flex-1" />
          <Button size="sm" onClick={() => {
            const v = aliasInput.trim();
            if (v && !point.aliases.includes(v)) {
              onChange({ ...point, aliases: [...point.aliases, v] });
              setAliasInput("");
            }
          }}>添加</Button>
        </div>
      </Field>
    </div>
  );
}