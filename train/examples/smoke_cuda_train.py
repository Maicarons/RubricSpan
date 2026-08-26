"""M0-3 smoke test: tiny Transformer trained on a CUDA 12 GPU.

Verifies: CUDA available, forward/backward on GPU, loss decreasing, optimizer step.
"""
import time
import torch
import torch.nn as nn

def main() -> int:
    print(f"torch={torch.__version__} cuda_available={torch.cuda.is_available()}")
    if not torch.cuda.is_available():
        print("FAIL: CUDA not available")
        return 1
    dev = torch.device("cuda")
    print(f"device={torch.cuda.get_device_name(0)} cc={torch.cuda.get_device_capability(0)}")

    torch.manual_seed(42)
    # Tiny MRC-like model: embedding + transformer encoder + start/end heads
    V, D, L = 1000, 64, 4
    emb = nn.Embedding(V, D)
    enc = nn.TransformerEncoder(nn.TransformerEncoderLayer(D, 4, dim_feedforward=128, batch_first=True), L)
    head_s, head_e = nn.Linear(D, 1), nn.Linear(D, 1)
    emb.to(dev); enc.to(dev); head_s.to(dev); head_e.to(dev)
    params = list(emb.parameters()) + list(enc.parameters()) + list(head_s.parameters()) + list(head_e.parameters())
    opt = torch.optim.AdamW(params, lr=3e-4)

    x = torch.randint(0, V, (16, 48), device=dev)
    ys = torch.randint(0, 48, (16,), device=dev)
    ye = torch.randint(0, 48, (16,), device=dev)

    t0 = time.time()
    first_loss = None
    for step in range(20):
        h = enc(emb(x))
        ls = nn.functional.cross_entropy(head_s(h).squeeze(-1), ys)
        le = nn.functional.cross_entropy(head_e(h).squeeze(-1), ye)
        loss = ls + le
        if first_loss is None:
            first_loss = loss.item()
        opt.zero_grad(); loss.backward(); opt.step()
    torch.cuda.synchronize()
    dt = time.time() - t0

    print(f"steps=20 loss {first_loss:.4f} -> {loss.item():.4f} elapsed={dt:.2f}s ({20/dt:.1f} it/s)")
    mem = torch.cuda.max_memory_allocated(dev) / 1024**2
    print(f"peak_gpu_mem={mem:.1f} MiB")
    ok = loss.item() < first_loss
    print("PASS: CUDA train smoke test" if ok else "FAIL: loss did not decrease")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
