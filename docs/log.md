
## 2026-10-23 — headings on the two parameter panels

- Each -mini parameters panel's docs row gets a bold "Machine Interface
  Parameters" / "Optimization Algo Parameters" heading plus the selected
  env/algorithm name (updated from env_cb/algo_cb currentTextChanged).
  First version widened the panel past the tab (long env name, Open Docs
  clipped); then with QSizePolicy.Ignored it vanished, because the spacer
  took the room. Final: label Ignored + stretch 1, no spacer; tooltip has the
  full text. Checked by screenshot with both panels open.
