#!/usr/bin/env python3
"""Observe exact Python code entries per trusted unittest test; not a sandbox."""
import argparse
import contextlib
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
import types
import unittest

PIN='a1c7e02ada1224a09327eaeee3b5d7d5c7f9e4b969f645ddc33725c49167d814'
SCOPE=dict(files=128,entries=512,depth=8,file_bytes=1<<20,total_bytes=8<<20,seconds=20.0)


def encode(value):
    return (json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':'))+'\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def library():
    path=Path(__file__).resolve().parent.parent/'sentinel-lens-0'/'lens.py'
    if sha(path.read_bytes())!=PIN:
        raise ValueError('dependency mismatch')
    spec=importlib.util.spec_from_file_location('exercise_lens',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def constant(value):
    if isinstance(value,types.CodeType):
        return ['code',code_payload(value)]
    if isinstance(value,tuple):
        return ['tuple',[constant(v) for v in value]]
    if isinstance(value,frozenset):
        return ['frozenset',sorted((constant(v) for v in value),key=lambda x:encode(x))]
    if isinstance(value,bytes):
        return ['bytes',value.hex()]
    if isinstance(value,float):
        return ['float',value.hex()]
    if isinstance(value,complex):
        return ['complex',value.real.hex(),value.imag.hex()]
    return [type(value).__name__,repr(value)]


def code_payload(code):
    return dict(bytecode=code.co_code.hex(),constants=[constant(x) for x in code.co_consts],
                names=code.co_names,varnames=code.co_varnames,freevars=code.co_freevars,
                cellvars=code.co_cellvars,flags=code.co_flags,args=code.co_argcount,
                posonly=code.co_posonlyargcount,kwonly=code.co_kwonlyargcount,
                exceptions=code.co_exceptiontable.hex())


def signature(code):
    return sha(encode(code_payload(code)))


def code_objects(code):
    for value in code.co_consts:
        if isinstance(value,types.CodeType):
            yield value
            yield from code_objects(value)


def worker(spec):
    lib=library()
    root=Path(spec['root']);out=Path(spec['out']);relative=spec['target_path'];qual=spec['qualname']
    result=dict(target=None,tests=[],unassigned_call_events=0,code_mismatch_events=0,
                profile_intact=False,tests_run=0,discovered_tests=0,test_result='UNKNOWN',gaps=[],
                python=sys.version.split()[0])
    raw=lib.read_at(root,relative,SCOPE['file_bytes'])
    if sha(raw)!=spec['target_sha256']:
        result['gaps'].append('TARGET_CHANGED_BEFORE_COMPILE');return result
    selected=[c for c in code_objects(compile(raw,str(root/relative),'exec',dont_inherit=True)) if c.co_qualname==qual]
    if len(selected)!=1:
        result['gaps'].append('TARGET_MISSING_OR_AMBIGUOUS');return result
    expected=selected[0]
    expected_sig=signature(expected)
    result['target']=dict(path=relative,qualname=qual,first_line=expected.co_firstlineno,
                          source_sha256=sha(raw),code_sha256=expected_sig)
    rows={};current=None;cache={}
    expected_path=str(root/relative)
    def profile(frame,event,arg):
        if event!='call':
            return
        code=frame.f_code
        if code.co_qualname!=qual or os.path.abspath(code.co_filename)!=expected_path:
            return
        key=id(code)
        if key not in cache:
            if len(cache)>=16:
                if 'CODE_VARIANT_LIMIT' not in result['gaps']:
                    result['gaps'].append('CODE_VARIANT_LIMIT')
                return
            cache[key]=(code,signature(code))
        if code.co_firstlineno!=expected.co_firstlineno or cache[key][1]!=expected_sig:
            result['code_mismatch_events']+=1;return
        if current is None:
            result['unassigned_call_events']+=1
        else:
            rows[current]['call_events']+=1

    class Observed(unittest.TestResult):
        def row(self,test):
            key=test.id()
            if key not in rows:
                rows[key]=dict(id=key,outcome='NOT_RUN',call_events=0)
            return rows[key]
        def startTest(self,test):
            nonlocal current
            super().startTest(test);self.row(test);current=test.id()
        def stopTest(self,test):
            nonlocal current
            current=None;super().stopTest(test)
        def addSuccess(self,test):
            super().addSuccess(test)
            if self.row(test)['outcome']=='NOT_RUN':
                self.row(test)['outcome']='PASS'
        def addFailure(self,test,err):
            super().addFailure(test,err);self.row(test)['outcome']='FAIL'
        def addError(self,test,err):
            super().addError(test,err);self.row(test)['outcome']='ERROR'
        def addSkip(self,test,reason):
            super().addSkip(test,reason);self.row(test)['outcome']='SKIP'
        def addExpectedFailure(self,test,err):
            super().addExpectedFailure(test,err);self.row(test)['outcome']='XFAIL'
        def addUnexpectedSuccess(self,test):
            super().addUnexpectedSuccess(test);self.row(test)['outcome']='XPASS'
        def addSubTest(self,test,subtest,outcome):
            super().addSubTest(test,subtest,outcome)
            if outcome is not None:
                self.row(test)['outcome']='FAIL' if issubclass(outcome[0],test.failureException) else 'ERROR'

    previous=sys.getprofile()
    if previous is not None:
        result['gaps'].append('OTHER_PROFILER_ACTIVE');return result
    sys.path.insert(0,str(root))
    stdout=open(out/'stdout.log','xb');stderr=open(out/'stderr.log','xb')
    # Text wrappers preserve the original stdout channel exclusively for our result.
    import io
    output=io.TextIOWrapper(stdout,encoding='utf-8');errors=io.TextIOWrapper(stderr,encoding='utf-8')
    try:
        with contextlib.redirect_stdout(output),contextlib.redirect_stderr(errors):
            sys.setprofile(profile)
            try:
                suite=unittest.TestLoader().discover(str(root),pattern=spec['pattern'],top_level_dir=str(root))
                cases=[]
                def flatten(group):
                    for item in group:
                        if isinstance(item,unittest.TestSuite):
                            yield from flatten(item)
                        else:
                            yield item
                for case in flatten(suite):
                    cases.append(case)
                    if len(cases)>spec['tests']:
                        result['gaps'].append('TEST_LIMIT');break
                result['discovered_tests']=len(cases)
                if not cases:
                    result['gaps'].append('NO_TESTS')
                elif not result['gaps']:
                    recorder=Observed()
                    for case in cases:
                        recorder.row(case)
                    unittest.TestSuite(cases).run(recorder)
                    result['tests_run']=recorder.testsRun
                    result['test_result']='PASS' if recorder.wasSuccessful() else 'FAIL'
            except BaseException:
                result['gaps'].append('DISCOVERY_OR_RUN_EXCEPTION')
            finally:
                result['profile_intact']=sys.getprofile() is profile
                sys.setprofile(previous)
    finally:
        output.close();errors.close()
    if not result['profile_intact']:
        result['gaps'].append('PROFILE_CHANGED')
    if result['code_mismatch_events']:
        result['gaps'].append('CODE_MISMATCH')
    result['tests']=[rows[k] for k in sorted(rows)]
    return result


def run(args,lib):
    if not args.target or ':' not in args.target:
        raise ValueError('target syntax')
    relative,qual=args.target.rsplit(':',1)
    lib.relative(relative)
    if not relative.endswith('.py') or not qual or len(qual.encode())>256:
        raise ValueError('invalid target')
    if Path(args.root,relative).absolute()==Path(__file__).resolve():
        raise ValueError('runner cannot target itself')
    if not args.pattern or '/' in args.pattern or '\\' in args.pattern or len(args.pattern)>128:
        raise ValueError('invalid pattern')
    if not 0<args.wall<=15 or not math.isfinite(args.wall) or not 0<args.cpu<=10 or not 1<=args.tests<=64 or not 1024<=args.log_bytes<=262144:
        raise ValueError('invalid worker limits')
    root,out,fd=lib.output_directory(args.root,args.out)
    manifest=dict(format='exercise-0-v1',engine_sha256=PIN,sources=[],inventory=[],gaps=[])
    spent=0
    def write(name,raw):
        nonlocal spent
        if spent+len(raw)>16<<20:
            raise ValueError('output cap')
        f=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        with os.fdopen(f,'wb') as stream:stream.write(raw)
        spent+=len(raw)
    try:
        inventory,gaps=lib.inventory(root,SCOPE,lib.Budget(SCOPE))
        manifest['inventory']=inventory;manifest['gaps']=gaps
        total=0;count=0
        for item in inventory:
            if item['kind']!='file':continue
            count+=1
            try:
                if count>SCOPE['files']:raise ValueError('file cap')
                raw=lib.read_at(root,item['path'],min(SCOPE['file_bytes'],SCOPE['total_bytes']-total))
                total+=len(raw);snapshot=sha(item['path'].encode())+'.source'
                write(snapshot,raw)
                manifest['sources'].append(dict(path=item['path'],sha256=sha(raw),snapshot=snapshot))
            except (OSError,ValueError,lib.Invalid):
                manifest['gaps'].append(dict(path=item['path'],reason='READ_OR_CAP_REFUSED'))
        original=encode(manifest);manifest_hash=sha(original);write('manifest.json',original)
        targets=[s for s in manifest['sources'] if s['path']==relative]
        observed=dict(target=None,tests=[],gaps=['INPUT_SCOPE_REFUSED'],test_result='UNKNOWN',unassigned_call_events=0)
        if not manifest['gaps'] and len(targets)==1:
            spec=dict(root=str(root),out=str(out),target_path=relative,qualname=qual,target_sha256=targets[0]['sha256'],pattern=args.pattern,tests=args.tests)
            def bound_child():
                resource.setrlimit(resource.RLIMIT_CPU,(args.cpu,args.cpu))
                resource.setrlimit(resource.RLIMIT_AS,(512<<20,512<<20))
                resource.setrlimit(resource.RLIMIT_FSIZE,(args.log_bytes,args.log_bytes))
                resource.setrlimit(resource.RLIMIT_CORE,(0,0))
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
            response=out/'worker-response.bin';diagnostics=out/'worker-diagnostics.log'
            with open(response,'xb') as output,open(diagnostics,'xb') as errors:
                try:
                    p=subprocess.run([sys.executable,str(Path(__file__).resolve()),'_worker'],input=encode(spec),
                                     cwd=root,env=env,stdout=output,stderr=errors,timeout=args.wall,preexec_fn=bound_child)
                    if p.returncode:raise ValueError('worker failed')
                    observed=json.loads(lib.read_at(out,response.name,args.log_bytes))
                except (ValueError,OSError,subprocess.TimeoutExpired):
                    observed['gaps']=['WORKER_RESULT_OR_LIMIT_GAP']
            for name in ('stdout.log','stderr.log','worker-response.bin','worker-diagnostics.log'):
                if (out/name).exists() and (out/name).stat().st_size>=args.log_bytes:
                    if 'LOG_LIMIT' not in observed['gaps']:observed['gaps'].append('LOG_LIMIT')
        elif not targets:
            observed['gaps']=['TARGET_NOT_IN_SCOPE']
        integrity_errors=[]
        after,after_gaps=lib.inventory(root,SCOPE,lib.Budget(SCOPE))
        if after!=inventory:integrity_errors.append('INVENTORY_CHANGED')
        if lib.read_at(out,'manifest.json',2<<20)!=original:integrity_errors.append('MANIFEST_CHANGED')
        for source in manifest['sources']:
            try:
                current=lib.read_at(root,source['path'],SCOPE['file_bytes'])
                retained=lib.read_at(out,source['snapshot'],SCOPE['file_bytes'])
                if sha(current)!=source['sha256'] or retained!=current:
                    integrity_errors.append('SOURCE_OR_SNAPSHOT_CHANGED')
            except (OSError,ValueError,lib.Invalid):
                integrity_errors.append('SOURCE_OR_SNAPSHOT_UNREADABLE')
        integrity='FAIL' if integrity_errors else 'INCOMPLETE' if manifest['gaps'] or after_gaps else 'PASS'
        if observed.get('target') and observed['target']['source_sha256']!=targets[0]['sha256']:
            integrity='FAIL';integrity_errors.append('TARGET_BINDING_MISMATCH')
        rows=observed.get('tests',[])
        yes=[r['id'] for r in rows if r['call_events']>0]
        no=[r['id'] for r in rows if r['call_events']==0]
        gaps=observed['gaps']
        status='INCOMPLETE' if gaps or integrity!='PASS' else 'OBSERVED_WITH_FAILURE' if yes and observed['test_result']=='FAIL' else 'OBSERVED' if yes else 'NOT_OBSERVED_IN_SCOPE'
        packet=dict(status=status,integrity=integrity,integrity_errors=sorted(set(integrity_errors)),test_result=observed.get('test_result','UNKNOWN'),
                    target=observed.get('target') or dict(path=relative,qualname=qual),manifest_sha256=manifest_hash,
                    observed_tests=yes[:8],not_observed_tests=no[:8],observed_test_count=len(yes),not_observed_test_count=len(no),
                    test_details_omitted=len(yes)>8 or len(no)>8,tests_run=observed.get('tests_run',0),
                    unassigned_call_events=observed.get('unassigned_call_events',0),gaps=gaps,
                    scope='Main-thread Python call events during unittest contexts; not line/branch/assertion coverage.',
                    warnings=['Setup/teardown calls count; discovery/class-hook calls are unassigned.','Other threads/processes and temporarily disabled profiling can hide calls. Trusted tests only; not an OS sandbox.'],
                    artifacts=dict(manifest='manifest.json',result='result.json'))
        # Keep the full measured result local, including statuses for every test.
        spent=sum(p.stat(follow_symlinks=False).st_size for p in out.iterdir())
        write('result.json',encode(observed))
        while len(encode(packet))>8192 and (packet['not_observed_tests'] or packet['observed_tests']):
            (packet['not_observed_tests'] or packet['observed_tests']).pop();packet['test_details_omitted']=True
        if len(encode(packet))>8192:raise ValueError('packet cap')
        write('packet.json',encode(packet))
        code=2 if status=='INCOMPLETE' else 0 if status=='OBSERVED' else 1
        return packet,code
    finally:
        os.close(fd)


class Deadline(BaseException):pass


def timeout(_s,_f):raise Deadline()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('run')
    for key in ('root','target','out'):p.add_argument('--'+key,required=True)
    p.add_argument('--pattern',default='test_*.py');p.add_argument('--tests',type=int,default=64)
    p.add_argument('--wall',type=float,default=10);p.add_argument('--cpu',type=int,default=5)
    p.add_argument('--log-bytes',type=int,default=262144)
    args=parser.parse_args(argv)
    try:
        if any('..' in Path(v).parts for v in (args.root,args.out)):
            raise ValueError('parent traversal')
        signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,20)
        packet,code=run(args,library())
    except OSError as exc:
        packet,code=dict(status='ERROR',integrity='UNKNOWN',error_code='OUTPUT_EXISTS' if exc.errno==17 else 'PATH_REFUSED',os_errno=exc.errno),2
    except (Exception,Deadline):
        packet,code=dict(status='INCOMPLETE',integrity='UNKNOWN',error_code='SCOPE_TARGET_OR_RESOURCE_REFUSED'),2
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    sys.stdout.buffer.write(encode(packet));return code


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='_worker':
        try:
            spec=json.loads(sys.stdin.buffer.read(1<<20));value=worker(spec)
            sys.stdout.buffer.write(encode(value))
        except BaseException:
            raise SystemExit(2)
    else:raise SystemExit(main())
