"""Minimal protocol fixture: validates native ACP persistence and permissions."""
import json,sys
turn=0
for line in sys.stdin:
    frame=json.loads(line)
    if 'method' not in frame:
        if frame.get('id')=='permission':
            print(json.dumps({'jsonrpc':'2.0','id':prompt_id,'result':{'stopReason':'end_turn'}}),flush=True)
        continue
    method=frame['method'];result={}
    if method=='initialize':result={'protocolVersion':1,'agentCapabilities':{'sessionCapabilities':{'resume':{}}} if '--resume' in sys.argv else {'loadSession':True}}
    elif method in ('session/new','session/load','session/resume'):
        result={'sessionId':frame['params'].get('sessionId','fixture-session')}
        if '--resume' in sys.argv and method=='session/load':
            print(json.dumps({'jsonrpc':'2.0','id':frame['id'],'error':{'message':'load is not supported'}}),flush=True)
            continue
        if method=='session/resume':result={}
        if method=='session/load':
            print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'OLD_HISTORY_REPLAY'}}}}),flush=True)
    elif method=='session/prompt':
        prompt_id=frame['id'];turn+=1
        print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'update':{'sessionUpdate':'tool_call','toolCallId':'fixture-read','title':'read_fixture','rawInput':{'path':'fixture'},'status':'in_progress'}}}),flush=True)
        print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':'fixture-session','update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'turn-'+str(turn)}}}}),flush=True)
        print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'update':{'sessionUpdate':'tool_call_update','toolCallId':'fixture-read','status':'completed','rawOutput':'fixture-result'}}}),flush=True)
        call={'toolCallId':'fixture-read'} if '--id-only' in sys.argv else {'title':'fixture-write','rawInput':{'file':'bounded-test'}}
        print(json.dumps({'jsonrpc':'2.0','id':'permission','method':'session/request_permission','params':{'toolCall':call,'options':[{'kind':'allow_once','optionId':'yes'},{'kind':'reject_once','optionId':'no'}]}}),flush=True)
        continue
    print(json.dumps({'jsonrpc':'2.0','id':frame['id'],'result':result}),flush=True)
