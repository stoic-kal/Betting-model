import sys, os, time, importlib.util

DIAG_DIR = os.path.dirname(os.path.abspath(__file__))
if DIAG_DIR not in sys.path:
    sys.path.insert(0, DIAG_DIR)

SECTIONS = [
    ("SECTION 1  — Data Health Audit", "01_data_health", "run"),
    ("SECTIONS 2-5 — Prediction & Calibration", "02_05_prediction_calibration", "run"),
    ("SECTIONS 6-12 — OVER/UNDER & Features", "06_12_over_under_features_teams", "run"),
    ("SECTIONS 13-25 — Root Cause & Roadmap", "13_25_root_cause_roadmap", "run"),
]


def _preload_loader():

    loader_path = os.path.join(DIAG_DIR, "00_loader.py")
    spec = importlib.util.spec_from_file_location("loader", loader_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["loader"] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    _preload_loader()
    print("\n" + "█" * 70)
    print("  MLB TOTALS MODEL — FULL DIAGNOSTIC SUITE")
    print("  Jingleez Picks | Quantitative Research")
    print("█" * 70)
    start = time.time()
    for label, module, fn in SECTIONS:
        print(f"\n{'▶'*3} {label}")
        try:
            spec = importlib.util.spec_from_file_location(
                module, os.path.join(DIAG_DIR, module + ".py")
            )
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module] = mod
            spec.loader.exec_module(mod)
            getattr(mod, fn)()
        except Exception as e:
            import traceback

            print(f"  FAILED: {e}")
            traceback.print_exc()
    elapsed = time.time() - start
    print(f"\n\n{'█'*70}")
    print(f"  DIAGNOSTIC COMPLETE in {elapsed:.1f}s")
    from pathlib import Path

    fig_dir = Path(__file__).parent / "figures"
    figs = list(fig_dir.glob("*.png"))
    print(f"  {len(figs)} figures saved to {fig_dir}")
    for f in sorted(figs):
        print(f"    {f.name}")
    print("█" * 70 + "\n")


if __name__ == "__main__":
    main()
