#!/usr/bin/env python3
import os, sys, json, time
log = os.environ["AGY_FAKE_LOG"]
n = sum(1 for _ in open(log)) if os.path.exists(log) else 0
open(log, "a").write(json.dumps(sys.argv[1:]) + "\n")
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
elif mode == "nostatus":  # JSON sem status e sem conversation_id: não é sucesso
    print(json.dumps({"response": "algo"}))
elif mode == "okexit1":  # JSON de sucesso, mas código de saída 1: não é sucesso
    print(json.dumps({"conversation_id": cid, "status": "OK", "response": "r", "error": ""})); sys.exit(1)
