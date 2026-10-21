#!/usr/bin/env python3
"""Bounded static candidate impact. Project sources are parsed, never executed."""
import argparse
import ast
from collections import Counter, deque
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace

PIN = 'a1c7e02ada1224a09327eaeee3b5d7d5c7f9e4b969f645ddc33725c49167d814'
CAPS = dict(files=128, entries=512, depth=8, file_bytes=1<<20, total_bytes=16<<20,
            output_bytes=16<<20, seconds=30.0, nodes=100000, calls=2048, hops=8)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(obj):
    return (json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(',', ':'))+'\n').encode()


def lens():
    p = Path(__file__).resolve().parent.parent/'sentinel-lens-0'/'lens.py'
    if sha(p.read_bytes()) != PIN:
        raise ValueError('dependency mismatch')
    spec = importlib.util.spec_from_file_location('impact_lens', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def parse_source(raw, module, package):
    """Child process only; contains no import/eval/exec of target source."""
    if raw.startswith(b'\xef\xbb\xbf'):
        raise ValueError('UTF-8 BOM unsupported')
    tree = ast.parse(raw.decode('utf-8', 'strict'), feature_version=(3, 12))
    nodes = sum(1 for _ in ast.walk(tree))
    if nodes > 10000:
        raise ValueError('per-file AST node cap')
    lines = raw.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1]+len(line))
    bindings, definitions, calls = {}, [], []
    star = False

    def bind(name, target):
        bindings.setdefault(name, []).append(target)

    class Binds(ast.NodeVisitor):
        def __init__(self):
            self.names = set()
        def visit_Name(self, node):
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                self.names.add(node.id)
        def visit_FunctionDef(self, node):
            self.names.add(node.name)
            for expression in node.decorator_list + node.args.defaults + [x for x in node.args.kw_defaults if x is not None]:
                self.visit(expression)
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_ClassDef(self, node):
            self.names.add(node.name)
        def visit_Import(self, node):
            self.names.update(a.asname or a.name.split('.')[0] for a in node.names)
        def visit_ImportFrom(self, node):
            self.names.update(a.asname or a.name for a in node.names)
        def visit_ExceptHandler(self, node):
            if node.name:
                self.names.add(node.name)
            self.generic_visit(node)
        def visit_MatchAs(self, node):
            if node.name:
                self.names.add(node.name)
            self.generic_visit(node)
        visit_MatchStar = visit_MatchAs
        def visit_MatchMapping(self, node):
            if node.rest:
                self.names.add(node.rest)
            self.generic_visit(node)
        def visit_Lambda(self, node):
            pass

    function_nodes = []
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bind(statement.name, None if statement.decorator_list else module+'.'+statement.name)
            function_nodes.append((module+'.'+statement.name, statement))
            default_bindings = Binds(); default_bindings.visit(statement)
            for rebound in default_bindings.names - {statement.name}:
                bind(rebound, None)
        elif isinstance(statement, ast.Import):
            for a in statement.names:
                bind(a.asname or a.name.split('.')[0], a.name if a.asname else a.name.split('.')[0])
        elif isinstance(statement, ast.ImportFrom):
            prefix = statement.module or ''
            valid_relative = True
            if statement.level:
                parts = package.split('.') if package else []
                if statement.level > len(parts):
                    valid_relative = False
                else:
                    prefix = '.'.join(parts[:len(parts)-statement.level+1]+([prefix] if prefix else []))
            for a in statement.names:
                if a.name == '*':
                    star = True
                else:
                    bind(a.asname or a.name, prefix+'.'+a.name if valid_relative else None)
        else:
            b = Binds(); b.visit(statement)
            if '*' in b.names:
                star = True
            for name in b.names:
                bind(name, None)
            if isinstance(statement, ast.ClassDef):
                for method in statement.body:
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        function_nodes.append((module+'.'+statement.name+'.'+method.name, method))
    global_map = {k:v[0] for k,v in bindings.items() if len(v)==1 and v[0] is not None}

    def position(node):
        start = offsets[node.lineno-1]+node.col_offset
        end = offsets[node.end_lineno-1]+node.end_col_offset
        if not 0 <= start < end <= len(raw) or end-start > 512:
            raise ValueError('callee span cap')
        return dict(line=node.lineno, start=start, end=end, quote=raw[start:end].decode('utf-8'))

    class Visitor(ast.NodeVisitor):
        def __init__(self, owner, blocked):
            self.owner, self.blocked = owner, blocked
        def visit_FunctionDef(self, node):
            # Nested function bodies have a different lexical environment.
            pass
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_ClassDef(self, node):
            pass
        def visit_Lambda(self, node):
            pass
        def visit_Call(self, node):
            if len(calls) >= 512:
                raise ValueError('per-file call cap')
            expression, rest = node.func, []
            while isinstance(expression, ast.Attribute):
                rest.insert(0, expression.attr)
                expression = expression.value
            target, why = None, 'DYNAMIC_OR_EXTERNAL'
            if isinstance(expression, ast.Name):
                name = expression.id
                if name in self.blocked:
                    why = 'SHADOWED_LOCAL'
                elif star:
                    why = 'WILDCARD_IMPORT'
                elif name in global_map:
                    target = '.'.join([global_map[name]]+rest)
                    why = 'STATIC_NAME_BINDING'
                elif name in bindings:
                    why = 'SHADOWED_OR_AMBIGUOUS_GLOBAL'
            try:
                location = position(node.func)
            except ValueError:
                location = dict(line=node.lineno, start=0, end=0, quote='')
                target, why = None, 'SPAN_CAP'
            calls.append(dict(caller=self.owner, target=target, reason=why, **location))
            self.generic_visit(node)

    counts = Counter(name for name, _ in function_nodes)
    for name, fn in function_nodes:
        if counts[name] > 1:
            continue
        definitions.append(dict(id=name, line=fn.lineno, static_export=global_map.get(fn.name)==name))
        b = Binds()
        for statement in fn.body:
            b.visit(statement)
        b.names.update(a.arg for a in fn.args.posonlyargs+fn.args.args+fn.args.kwonlyargs)
        if fn.args.vararg:
            b.names.add(fn.args.vararg.arg)
        if fn.args.kwarg:
            b.names.add(fn.args.kwarg.arg)
        visitor = Visitor(name, b.names)
        for statement in fn.body:
            visitor.visit(statement)
    visitor = Visitor(module+'.<module>', set())
    for statement in tree.body:
        visitor.visit(statement)
    omitted = sum(isinstance(n, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree)) - len(function_nodes)
    return dict(nodes=nodes, definitions=definitions, calls=calls, nested_scopes_omitted=max(0, omitted))


def parse_child(raw, module, package):
    def bounded():
        resource.setrlimit(resource.RLIMIT_CPU, (2,2))
        resource.setrlimit(resource.RLIMIT_AS, (256<<20,256<<20))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1<<20,1<<20))
        resource.setrlimit(resource.RLIMIT_CORE, (0,0))
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        p = subprocess.run([sys.executable, str(Path(__file__).resolve()), '_parse', module, package],
                           input=raw, stdout=out, stderr=err, timeout=3, preexec_fn=bounded)
        if p.returncode:
            raise ValueError('parser refused source or cap')
        out.seek(0)
        data = out.read((1<<20)+1)
        if len(data)>1<<20:
            raise ValueError('parser output cap')
        return json.loads(data)


def module_name(path):
    parts = list(Path(path).with_suffix('').parts)
    is_package = parts[-1]=='__init__'
    if is_package:
        parts.pop()
    module = '.'.join(parts) or '__root__'
    return module, module if is_package else '.'.join(parts[:-1])


def verify_graph(root, out, expected, lib):
    errors = []
    raw = lib.read_at(out, 'graph.json', 2<<20)
    if sha(raw)!=expected:
        return dict(mechanical='FAIL',errors=['graph hash mismatch'])
    g = json.loads(raw)
    if g['format']!='impact-0-v1' or g['engine_sha256']!=PIN:
        raise ValueError('graph format or dependency pin mismatch')
    limits = g['limits']
    for key, value in limits.items():
        if key not in CAPS or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<value<=CAPS[key]:
            raise ValueError('invalid graph limits')
    inventory, gaps = lib.inventory(root, limits, lib.Budget(limits))
    if inventory!=g['inventory']:
        errors.append('source inventory changed')
    sources = {}
    for s in g['sources']:
        try:
            data = lib.read_at(root,s['path'],limits['file_bytes'])
            retained = lib.read_at(out,s['snapshot'],limits['file_bytes'])
            if sha(data)!=s['sha256'] or retained!=data:
                errors.append('source/snapshot changed: '+s['path'])
            sources[s['path']]=data
        except (OSError,ValueError,lib.Invalid):
            errors.append('source/snapshot unreadable: '+s['path'])
    for edge in g['edges']:
        try:
            data=sources[edge['path']]
            if sha(data)!=edge['source_sha256'] or lib.span(data,edge['start'],edge['end'])!=edge['quote']:
                errors.append('edge span/source mismatch')
        except (KeyError,ValueError,lib.Invalid):
            errors.append('edge span/source invalid')
    return dict(mechanical='FAIL' if errors else 'INCOMPLETE' if gaps or g['gaps'] else 'PASS',errors=errors)


def trace(args, lib):
    limits={k:getattr(args,k) for k in CAPS}
    for k,v in limits.items():
        if not math.isfinite(v) or not 0<v<=CAPS[k]:
            raise ValueError('invalid limits')
    root,out,fd=lib.output_directory(args.root,args.out)
    budget=lib.Budget(limits)
    spent=0
    def write(name,data):
        nonlocal spent
        if len(data)+spent>limits['output_bytes']:
            raise ValueError('derived output cap')
        f=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        with os.fdopen(f,'wb') as stream:
            stream.write(data)
        spent+=len(data)
    try:
        inventory,gaps=lib.inventory(root,limits,budget)
        paths=[r['path'] for r in inventory if r['kind']=='file' and r['path'].endswith('.py')]
        modules=Counter(module_name(p)[0] for p in paths)
        graph=dict(format='impact-0-v1',engine_sha256=PIN,limits=limits,inventory=inventory,sources=[],definitions=[],edges=[],unknowns=[],gaps=gaps,candidates=[],nested_scopes_omitted=0)
        records=[]; total=nodes=0
        for index,path in enumerate(paths):
            budget.remaining()
            try:
                if index>=limits['files']:
                    raise ValueError('file count cap')
                data=lib.read_at(root,path,min(limits['file_bytes'],limits['total_bytes']-total))
                total+=len(data)
                snapshot=sha(path.encode())+'.utf8'
                write(snapshot,data)
                source=dict(path=path,sha256=sha(data),snapshot=snapshot)
                graph['sources'].append(source)
                module,package=module_name(path)
                if modules[module]>1:
                    raise ValueError('ambiguous module identity')
                parsed=parse_child(data,module,package)
                nodes+=parsed['nodes']
                if nodes>limits['nodes']:
                    raise ValueError('aggregate AST node cap')
                if len(graph['definitions'])+len(parsed['definitions'])>1024:
                    raise ValueError('function symbol cap')
                for definition in parsed['definitions']:
                    graph['definitions'].append(dict(**definition,path=path))
                graph['nested_scopes_omitted']+=parsed['nested_scopes_omitted']
                for call in parsed['calls']:
                    if len(records)>=limits['calls']:
                        raise ValueError('aggregate call cap')
                    records.append(dict(**call,path=path,source_sha256=source['sha256']))
            except (OSError,ValueError,lib.Invalid,subprocess.TimeoutExpired):
                graph['gaps'].append(dict(path=path,reason='SOURCE_PARSE_OR_LIMIT_GAP'))
        known={d['id'] for d in graph['definitions']}
        callable_exports={d['id'] for d in graph['definitions'] if d['static_export']}
        for call in records:
            target=call.pop('target')
            if target in callable_exports and call['end']>call['start']:
                graph['edges'].append(dict(**call,callee=target,id=len(graph['edges'])))
            else:
                call['reason']='UNPROVEN_EXPORT_OR_EXTERNAL' if target else call['reason']
                call['candidate_name']=target
                graph['unknowns'].append(call)
        reverse={}
        for e in graph['edges']:
            reverse.setdefault(e['callee'],[]).append(e)
        queue=deque([(args.symbol,0)]); seen={args.symbol}; truncated=False
        while queue:
            target,distance=queue.popleft()
            for edge in sorted(reverse.get(target,[]),key=lambda e:(e['caller'],e['path'],e['start'])):
                caller=edge['caller']
                if caller in seen:
                    continue
                if distance>=limits['hops']:
                    truncated=True; continue
                seen.add(caller)
                candidate=dict(symbol=caller,distance=distance+1,via=target,edge=edge['id'],candidate_test=caller.split('.')[-1].startswith('test'))
                graph['candidates'].append(candidate)
                queue.append((caller,distance+1))
        graph['symbol']=args.symbol
        graph['trace_truncated']=truncated
        graph['ignored_non_python_files']=sum(r['kind']=='file' and not r['path'].endswith('.py') for r in inventory)
        raw=encode(graph)
        if len(raw)>2<<20:
            raise ValueError('graph output cap')
        write('graph.json',raw)
        verification=verify_graph(root,out,sha(raw),lib)
        status='CANDIDATES' if graph['candidates'] else 'UNKNOWN_SYMBOL' if args.symbol not in known else 'NO_STATIC_CALLERS_FOUND'
        report=dict(status=status,symbol=args.symbol,mechanical=verification['mechanical'],analysis='STATIC_PARTIAL',semantic='REVIEW_REQUIRED',
                    candidates=[dict(**c, evidence={k:graph['edges'][c['edge']][k] for k in ('path','line','start','end','quote','source_sha256')}) for c in graph['candidates'][:12]],candidate_count=len(graph['candidates']),trace_truncated=truncated or len(graph['candidates'])>12,
                    graph_sha256=sha(raw),source_count=len(graph['sources']),edge_count=len(graph['edges']),unknown_count=len(graph['unknowns']),
                    gap_count=len(graph['gaps']),gaps=graph['gaps'][:3],gap_details_omitted=len(graph['gaps'])>3,errors=verification['errors'][:2],
                    warnings=['Syntactic candidates are not proven runtime calls or test coverage.','Dynamic dispatch, nested scopes, rebinding and missing sources can hide impact.'],artifact='graph.json')
        while len(encode(report))>8192 and report['candidates']:
            report['candidates'].pop();report['trace_truncated']=True
        if len(encode(report))>8192:
            raise ValueError('packet output cap')
        write('report.json',encode(report))
        return report,2 if verification['mechanical']=='FAIL' else 1 if verification['mechanical']=='INCOMPLETE' or status!='CANDIDATES' else 0
    finally:
        os.close(fd)


class Deadline(BaseException):
    pass


def timeout(_s,_f):
    raise Deadline()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('trace');p.add_argument('--symbol',required=True)
    for k,v in CAPS.items():
        p.add_argument('--'+k.replace('_','-'),type=float if k=='seconds' else int,default=4 if k=='hops' else v)
    v=sub.add_parser('verify');v.add_argument('--graph-sha256',required=True)
    for command in (p,v):
        command.add_argument('--root',required=True);command.add_argument('--out',required=True)
    args=parser.parse_args(argv)
    try:
        if any('..' in Path(x).parts for x in (args.root,args.out)):
            raise ValueError('parent traversal refused')
        seconds=getattr(args,'seconds',30)
        if not math.isfinite(seconds) or not 0<seconds<=30:
            raise ValueError('invalid deadline')
        signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,seconds)
        lib=lens()
        if args.command=='trace':
            result,code=trace(args,lib)
        else:
            result=verify_graph(args.root,args.out,args.graph_sha256,lib)
            code={'PASS':0,'INCOMPLETE':1,'FAIL':2}[result['mechanical']]
    except Deadline:
        result,code=dict(status='ERROR',mechanical='FAIL',error_code='TIME_LIMIT',analysis='STATIC_PARTIAL',semantic='REVIEW_REQUIRED'),2
    except OSError as exc:
        result,code=dict(status='ERROR',mechanical='FAIL',error_code='OUTPUT_EXISTS' if exc.errno==17 else 'PATH_REFUSED',os_errno=exc.errno,analysis='STATIC_PARTIAL',semantic='REVIEW_REQUIRED',error='Choose an approved source and a fresh separate output directory.'),2
    except Exception:
        result,code=dict(status='ERROR',mechanical='FAIL',error_code='SCOPE_OR_RESOURCE_REFUSED',analysis='STATIC_PARTIAL',semantic='REVIEW_REQUIRED',error='Scope, integrity, syntax or resource limit refused; no safe-to-edit conclusion.'),2
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
    if len(encode(result))>8192 and isinstance(result.get('errors'),list):
        result['error_count']=len(result['errors'])
        result['error_details_omitted']=True
        while result['errors'] and len(encode(result))>8192:
            result['errors'].pop()
    if len(encode(result))>8192:
        result,code=dict(status='ERROR',mechanical='FAIL',error_code='PACKET_LIMIT',analysis='STATIC_PARTIAL'),2
    sys.stdout.buffer.write(encode(result))
    return code


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='_parse':
        try:
            raw=sys.stdin.buffer.read((1<<20)+1)
            if len(raw)>1<<20:
                raise ValueError('input cap')
            sys.stdout.buffer.write(encode(parse_source(raw,sys.argv[2],sys.argv[3])))
        except Exception:
            raise SystemExit(2)
    else:
        raise SystemExit(main())
