#!/usr/bin/env python3
"""Fixed-target, read-only validation of the actual production Caddy container."""
from __future__ import annotations
import hashlib, ipaddress, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from typing import Any
CONTAINER='codestra-caddy'; DOCKER='/usr/bin/docker'; CURL='/usr/bin/curl'; SS='/usr/bin/ss'
EXPECTED_IMAGE_REPOSITORY='ghcr.io/appolon1908-hue/codestra-caddy'
EXPECTED_SOURCE_REPOSITORY='https://github.com/appolon1908-hue/Caddy'
SOURCE_LABEL='io.codestra.caddy.source.sha'; DIGEST_LABEL='io.codestra.caddy.image.digest'; CONFIG_LABEL='io.codestra.caddy.config.sha256'; RELEASE_LABEL='io.codestra.caddy.release.id'; IMAGE_CONFIG_LABEL='io.codestra.caddy.config.sha256'
REQUIRED_MODULES={'http.handlers.reverse_proxy','http.handlers.headers','http.handlers.metrics','tls'}
REQUIRED_ENVIRONMENT={
'CADDY_PUBLIC_BIND','CADDY_PRIVATE_METRICS_BIND','CADDY_PRIVATE_INGRESS_BIND','CADDY_KLYROW_SOURCE_CIDRS','CADDY_VICIDIAL_SOURCE_CIDRS','CADDY_STAGING_EVENT_SOURCE_CIDRS','CADDY_KONG_UPSTREAM','CADDY_REALTIME_UPSTREAM','CADDY_KEYCLOAK_UPSTREAM','CADDY_CRM_RESELLER_UPSTREAM','CADDY_CRM_UPSTREAM','CADDY_N8N_UPSTREAM','CADDY_N8N_STAGING_UPSTREAM','CADDY_STAGING_API_UPSTREAM','CADDY_STAGING_PORTAL_UPSTREAM','CADDY_STAGING_KEYCLOAK_UPSTREAM','CADDY_STAGING_ODOO_UPSTREAM','CADDY_MIDDLEWARE_CALLBACK_UPSTREAM','CADDY_AGENT_GATEWAY_UPSTREAM','CADDY_AGENT_UI_UPSTREAM','CADDY_MONITORING_UPSTREAM','CADDY_KLYROW_EVENTS_UPSTREAM','CADDY_EDITOR_ADMIN_CIDRS','CADDY_N8N_EDITOR_MAX_REQUEST_BODY','CADDY_GRAFANA_UPSTREAM','CADDY_SUPERSET_UPSTREAM','CADDY_OPENBAO_UPSTREAM','CADDY_OPENBAO_ALLOWED_CIDRS'}
UPSTREAM_ENVIRONMENT={n for n in REQUIRED_ENVIRONMENT if n.endswith('_UPSTREAM')}
IP_ENVIRONMENT={'CADDY_PUBLIC_BIND','CADDY_PRIVATE_METRICS_BIND','CADDY_PRIVATE_INGRESS_BIND'}
CIDR_ENVIRONMENT={n for n in REQUIRED_ENVIRONMENT if n.endswith('_CIDRS')}
class ValidationError(RuntimeError): pass
def run(command:list[str],*,timeout:int=30)->str:
    result=subprocess.run(command,check=False,capture_output=True,text=True,timeout=timeout,env={'PATH':'/usr/bin:/bin'})
    if result.returncode!=0: raise ValidationError(f'fixed command failed: {Path(command[0]).name}')
    return result.stdout
def parse_environment(entries:list[str])->dict[str,str]:
    out={}
    for entry in entries:
        if '=' in entry:
            name,value=entry.split('=',1); out[name]=value
    return out
def validate_environment(environment:dict[str,str])->None:
    missing=sorted(n for n in REQUIRED_ENVIRONMENT if not environment.get(n))
    if missing: raise ValidationError(f"required runtime environment missing: {','.join(missing)}")
    for name in IP_ENVIRONMENT: ipaddress.ip_address(environment[name])
    for name in CIDR_ENVIRONMENT:
        for value in environment[name].split(): ipaddress.ip_network(value,strict=False)
    for name in UPSTREAM_ENVIRONMENT:
        if not re.fullmatch(r'(?:[A-Za-z0-9_.-]+|\[[0-9A-Fa-f:]+\]):[0-9]{1,5}',environment[name]): raise ValidationError(f'invalid upstream environment: {name}')
        if not 1<=int(environment[name].rsplit(':',1)[1])<=65535: raise ValidationError(f'invalid upstream port: {name}')
    if not environment['CADDY_N8N_EDITOR_MAX_REQUEST_BODY'].isdigit(): raise ValidationError('invalid editor request-body limit')
def config_tree_hash(root:Path)->str:
    digest=hashlib.sha256(); count=0
    for path in sorted(root.rglob('*'),key=lambda item:item.as_posix()):
        relative=path.relative_to(root)
        if relative.parts and relative.parts[0]=='private': continue
        if path.is_symlink(): raise ValidationError('container configuration contains a symbolic link')
        if not path.is_file(): continue
        payload=path.read_bytes(); name=relative.as_posix().encode()
        digest.update(len(name).to_bytes(8,'big')); digest.update(name); digest.update(len(payload).to_bytes(8,'big')); digest.update(payload); count+=1
    if count==0: raise ValidationError('container configuration tree is empty')
    return digest.hexdigest()
def require_listener(table:str,protocol:str,port:int)->None:
    if not re.search(rf'^{protocol}\s+.*(?:\]|:){port}\s',table,re.MULTILINE): raise ValidationError(f'required listener missing: {protocol}/{port}')
def adapted_summary(adapted:dict[str,Any])->dict[str,int]:
    counters={'servers':len((((adapted.get('apps') or {}).get('http') or {}).get('servers') or {})),'routes':0,'upstreams':0,'access_logs':len(((adapted.get('logging') or {}).get('logs') or {})),'tls_policies':0}
    def visit(value:Any)->None:
        if isinstance(value,dict):
            if isinstance(value.get('routes'),list): counters['routes']+=len(value['routes'])
            if isinstance(value.get('upstreams'),list): counters['upstreams']+=len(value['upstreams'])
            if isinstance(value.get('tls_connection_policies'),list): counters['tls_policies']+=len(value['tls_connection_policies'])
            for child in value.values(): visit(child)
        elif isinstance(value,list):
            for child in value: visit(child)
    visit(adapted); return counters
def main()->int:
    if len(sys.argv)!=1: raise ValidationError('arguments are not accepted')
    for binary in (DOCKER,CURL,SS):
        if not Path(binary).is_file() or os.path.islink(binary): raise ValidationError(f'trusted executable unavailable: {Path(binary).name}')
    inspected=json.loads(run([DOCKER,'inspect',CONTAINER]));
    if len(inspected)!=1: raise ValidationError('fixed Caddy container not found')
    container=inspected[0]; state=container.get('State') or {}; health=state.get('Health') or {}
    if state.get('Running') is not True: raise ValidationError('Caddy container is not running')
    if health.get('Status')!='healthy': raise ValidationError('Caddy container health is not healthy')
    config=container.get('Config') or {}; image_reference=config.get('Image') or ''
    match=re.fullmatch(rf'{re.escape(EXPECTED_IMAGE_REPOSITORY)}@(sha256:[0-9a-f]{{64}})',image_reference)
    if not match: raise ValidationError('container image is not the immutable canonical identity')
    image_digest=match.group(1); labels=config.get('Labels') or {}; source_sha=labels.get(SOURCE_LABEL) or ''; config_sha=labels.get(CONFIG_LABEL) or ''
    if not re.fullmatch(r'[0-9a-f]{40}',source_sha): raise ValidationError('container source SHA label is invalid')
    if labels.get(DIGEST_LABEL)!=image_digest: raise ValidationError('container image digest label does not match the image')
    if not re.fullmatch(r'[0-9a-f]{64}',config_sha): raise ValidationError('container configuration digest label is invalid')
    if not labels.get(RELEASE_LABEL): raise ValidationError('container release identity is missing')
    images=json.loads(run([DOCKER,'image','inspect',image_reference]));
    if len(images)!=1: raise ValidationError('immutable Caddy image is unavailable locally')
    image=images[0]
    if image_reference not in (image.get('RepoDigests') or []): raise ValidationError('local image repository digest does not match')
    image_labels=((image.get('Config') or {}).get('Labels') or {})
    if image_labels.get('org.opencontainers.image.source')!=EXPECTED_SOURCE_REPOSITORY: raise ValidationError('image source label is not canonical')
    if image_labels.get('org.opencontainers.image.revision')!=source_sha: raise ValidationError('image revision label does not match container source')
    if image_labels.get(IMAGE_CONFIG_LABEL)!=config_sha: raise ValidationError('image configuration label does not match container label')
    if (image.get('Config') or {}).get('User')!='65532:65532': raise ValidationError('image runtime user is not non-root')
    environment=parse_environment(config.get('Env') or []); validate_environment(environment)
    run([DOCKER,'exec',CONTAINER,'/usr/bin/caddy','validate','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'])
    adapted=json.loads(run([DOCKER,'exec',CONTAINER,'/usr/bin/caddy','adapt','--config','/etc/caddy/Caddyfile','--adapter','caddyfile']))
    modules={line.split()[0] for line in run([DOCKER,'exec',CONTAINER,'/usr/bin/caddy','list-modules','--packages']).splitlines() if line.strip()}
    missing=sorted(REQUIRED_MODULES-modules)
    if missing: raise ValidationError(f"required Caddy modules missing: {','.join(missing)}")
    copied=Path(tempfile.mkdtemp(prefix='codestra-caddy-config-'))
    try:
        run([DOCKER,'cp',f'{CONTAINER}:/etc/caddy/.',str(copied)],timeout=60); actual=config_tree_hash(copied)
    finally: shutil.rmtree(copied,ignore_errors=True)
    if actual!=config_sha: raise ValidationError('running configuration checksum does not match the signed image')
    sockets=run([SS,'-H','-lntup']); require_listener(sockets,'tcp',80); require_listener(sockets,'tcp',443); require_listener(sockets,'udp',443); require_listener(sockets,'tcp',2020)
    metrics_ip=ipaddress.ip_address(environment['CADDY_PRIVATE_METRICS_BIND'])
    if not metrics_ip.is_private: raise ValidationError('metrics listener is not bound to a private address')
    run([CURL,'--fail','--silent','--show-error','--connect-timeout','3','--max-time','5',f'http://{metrics_ip}:2020/healthz'])
    evidence={'schema':'codestra.caddy-container-validation.v2','container':CONTAINER,'source_sha':source_sha,'image_digest':image_digest,'config_sha256':config_sha,'release_id':labels[RELEASE_LABEL],'container_running':True,'container_health':'healthy','image_signature_identity_required':True,'config_validation':'PASS','config_identity':'PASS','runtime_environment':sorted(REQUIRED_ENVIRONMENT),'module_set_sha256':hashlib.sha256('\n'.join(sorted(modules)).encode()).hexdigest(),'adapted':adapted_summary(adapted),'listeners':['tcp/80','tcp/443','udp/443','tcp/2020-private']}
    print(json.dumps(evidence,sort_keys=True,separators=(',',':'))); return 0
if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValidationError,OSError,ValueError,json.JSONDecodeError,subprocess.SubprocessError) as exc:
        print(f'CADDY_CONTAINER_VALIDATION=FAIL:{type(exc).__name__}:{exc}',file=sys.stderr); raise SystemExit(2)
