#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from pathlib import Path
from typing import Any
def visit(value:Any,counters:dict[str,int])->None:
    if isinstance(value,dict):
        if value.get('handler')=='reverse_proxy': counters['reverse_proxy_handlers']+=1
        if value.get('handler')=='metrics': counters['metrics_handlers']+=1
        for child in value.values(): visit(child,counters)
    elif isinstance(value,list):
        for child in value: visit(child,counters)
def main()->int:
    if len(sys.argv)!=2: print('usage: validate_adapted_config.py ADAPTED_JSON',file=sys.stderr); return 2
    adapted=json.loads(Path(sys.argv[1]).read_text()); servers=(((adapted.get('apps') or {}).get('http') or {}).get('servers') or {})
    if not servers: raise SystemExit('CADDY_ADAPTED_CONFIG=FAIL:no_http_servers')
    counters={'reverse_proxy_handlers':0,'metrics_handlers':0}; visit(adapted,counters)
    if counters['reverse_proxy_handlers']<10: raise SystemExit('CADDY_ADAPTED_CONFIG=FAIL:missing_reverse_proxy_handlers')
    if counters['metrics_handlers']<1: raise SystemExit('CADDY_ADAPTED_CONFIG=FAIL:missing_metrics_handler')
    logs=((adapted.get('logging') or {}).get('logs') or {})
    if len(logs)<5: raise SystemExit('CADDY_ADAPTED_CONFIG=FAIL:missing_access_logs')
    print(f"CADDY_ADAPTED_CONFIG=PASS servers={len(servers)} reverse_proxies={counters['reverse_proxy_handlers']} logs={len(logs)}"); return 0
if __name__=='__main__': raise SystemExit(main())
