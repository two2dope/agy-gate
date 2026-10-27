#!/usr/bin/env bash
# Roda todos os testes. Precisa de Python 3.12+ com tkinter e, sem tela, de xvfb.
#   Debian/Ubuntu: sudo apt install python3-tk xvfb
# Uso: tests/run_all.sh            (todos)
#      tests/run_all.sh test_theme (um só)
cd "$(dirname "$0")" || exit 1
PY="${PYTHON:-python3}"
RUN=("$PY" -I)
if [ -z "$DISPLAY" ]; then
  command -v xvfb-run >/dev/null || { echo "Sem tela e sem xvfb-run: instale xvfb."; exit 2; }
  RUN=(xvfb-run -a -s "-screen 0 1400x900x24" "$PY" -I)
fi
if [ $# -gt 0 ]; then files=("$@"); else files=(test_*.py); fi
fail=0
for f in "${files[@]}"; do
  f="${f%.py}"
  out="$("${RUN[@]}" "$f.py" 2>&1)"; code=$?
  if [ $code -eq 0 ] && grep -q "TODOS OS TESTES" <<<"$out"; then
    echo "ok     $f"
  else
    echo "FALHOU $f (código $code)"; grep -v "invalid command name\|while executing\|(\"after\" script)\|^\"" <<<"$out" | tail -12; fail=1
  fi
done
[ $fail -eq 0 ] && echo "Todos passaram." || { echo "Há falhas."; exit 1; }
