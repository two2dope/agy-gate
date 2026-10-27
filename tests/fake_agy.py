#!/usr/bin/env python3
import os, sys, json, time
log = os.environ["AGY_FAKE_LOG"]
n = sum(1 for _ in open(log)) if os.path.exists(log) else 0
open(log, "a").write(json.dumps(sys.argv[1:]) + "\n")
if os.environ.get("AGY_FAKE_CWD"):  # pasta de trabalho recebida (o agy real a registra como workspace)
    open(os.environ["AGY_FAKE_CWD"], "a").write(os.getcwd() + "\n")
seq = os.environ.get("AGY_FAKE_SEQ", "ok").split(",")
mode = seq[min(n, len(seq) - 1)]
cid = "aaaaaaaa-0000-0000-0000-%012d" % (n + 1)
if mode == "ok":
    print(json.dumps({"conversation_id": cid, "status": "OK", "response": "Entendi o objetivo.\nFalta o teste final.", "error": "", "duration_seconds": 3.2, "num_turns": 1,
                      "usage": {"input_tokens": 1200, "output_tokens": 80, "thinking_tokens": 40, "cache_read_tokens": 0, "total_tokens": 1320}}))
elif mode == "quota":
    msg = "Individual quota reached. Please upgrade your subscription to increase your limits. Resets in 31h40m31s."
    print("error: " + msg, file=sys.stderr)
    print('AGY_ERROR: {"short_error":"RESOURCE_EXHAUSTED (code 429): %s","status":"RESOURCE_EXHAUSTED","error_code":429,"code_kind":"http","retryable":true}' % msg, file=sys.stderr)
    print(json.dumps({"conversation_id": cid, "status": "ERROR", "response": "", "error": msg, "duration_seconds": 2.3, "num_turns": 1,
                      "usage": {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "cache_read_tokens": 0, "total_tokens": 0}}))
    sys.exit(1)
elif mode == "fail":
    print(json.dumps({"conversation_id": cid, "status": "ERROR", "response": "", "error": "falha qualquer", "usage": {}})); sys.exit(1)
elif mode == "garbage":
    print("banana sem json")
elif mode == "hang":
    time.sleep(60)
elif mode == "crash":
    sys.exit(2)
elif mode == "badmodel":  # saída real do agy (26/10) com nome de modelo sem o esforço
    msg = ('invalid model selection (--model "Gemini 3.8 Flash" --effort ""): model Gemini 3.8 Flash is not recognized as a known model or custom model in settings\n'
           'Available models:\n  Gemini 4 Argon (Medium)\n  Gemini 3.8 Flash (High)\n  Gemini 3.8 Flash (Medium)\n  Novo Modelo X (Low)')
    print("error: " + msg, file=sys.stderr)
    print(json.dumps({"conversation_id": "", "status": "ERROR", "response": "", "error": msg, "duration_seconds": 0, "num_turns": 0, "usage": {}}))
    sys.exit(1)
elif mode == "badmodel_creates":  # erro com conversation_id vazio, mas o agy criou a sessão mesmo assim
    import sqlite3  # como o agy real: a sessão nova começa com o prompt recebido (passo 14, f19.f2)
    def vi(x):
        o = bytearray()
        while True:
            b = x & 0x7f; x >>= 7
            if x: o.append(b | 0x80)
            else: o.append(b); return bytes(o)
    fl = lambda f, b: vi(f << 3 | 2) + vi(len(b)) + b
    c = sqlite3.connect(os.path.join(os.environ["AGY_FAKE_CONV"], "bbbbbbbb-0000-0000-0000-%012d.db" % (n + 1)))
    c.execute("CREATE TABLE steps (idx integer PRIMARY KEY, step_type integer, status integer, step_payload blob, error_details blob)")
    c.execute("INSERT INTO steps VALUES(0,14,3,?,NULL)", (fl(19, fl(2, ("/plan " + sys.argv[-1]).encode())),)); c.commit(); c.close()
    msg = 'invalid model selection (--model "X" --effort ""): model X is not recognized\nAvailable models:\n  Gemini 3.8 Flash (Medium)\n  Gemini 4 Argon (Medium)'
    print(json.dumps({"conversation_id": "", "status": "ERROR", "response": "", "error": msg})); sys.exit(1)
elif mode == "ok_with_sub":  # sucesso que cria também um sub-agente: nada é arquivado
    conv = os.environ["AGY_FAKE_CONV"]
    open(os.path.join(conv, cid + ".db"), "w").close(); open(os.path.join(conv, "cccccccc-0000-0000-0000-%012d.db" % (n + 1)), "w").close()
    print(json.dumps({"conversation_id": cid, "status": "OK", "response": "ok", "error": ""}))
elif mode == "denied":  # saída real de 26/10: SUCCESS sem resposta porque o modo sem janela negou read_file
    print(json.dumps({"conversation_id": cid, "status": "SUCCESS", "response": "", "duration_seconds": 15.2, "num_turns": 1,
                      "usage": {"input_tokens": 25314, "output_tokens": 791}, "denied_actions": [{"action": "read_file", "display_name": "ReadFile"}]}))
    print('jetski: no output produced — a tool required the "read_file" permission that headless mode cannot prompt for, so it was auto-denied.', file=sys.stderr)
elif mode == "nostatus":  # JSON sem status e sem conversation_id: não é sucesso
    print(json.dumps({"response": "algo"}))
elif mode == "okexit1":  # JSON de sucesso, mas código de saída 1: não é sucesso
    print(json.dumps({"conversation_id": cid, "status": "OK", "response": "r", "error": ""})); sys.exit(1)
