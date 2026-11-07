function yat_run(folder)
% Persistent coordinator for the supplied automotive-agent. Does not alter it.
runner=[]; registry=[]; done=false; revision=0; current=''; messages={};
try
    input=readJSON(fullfile(folder,'init.json'));
    addpath(input.project); autoAgentSetup(); cd(input.workspace);
    config=autoagent.Config.load(); registry=autoagent.ToolRegistry(config);
    if ~isempty(config.mcpServers) && any([config.mcpServers.enabled]) && any(strcmp({config.mcpServers.name},'matlab'))
        if isfile(fullfile(config.simulinkToolkitRoot,'satk_initialize.p'))
            addpath(config.simulinkToolkitRoot); satk_initialize(MCPServerPath=string(config.mcpBinary));
        end
        shareMATLABSession();
    end
    history=fullfile(folder,'history.json');
    if isfile(history), stored=readJSON(history); messages=stored.messages; end
    specs=registry.specs(); definitions=input.tools;
    if isstruct(definitions), definitions=num2cell(definitions); end
    for k=1:numel(definitions)
        d=definitions{k};
        specs(end+1)=struct('name',d.name,'description',d.description,'schema',d.inputSchema,'python',[]); %#ok<AGROW>
    end
    runner=autoagent.Runner(); runner.OnUpdate=@update; runner.OnTool=@tool;
    writeJSON(fullfile(folder,'ready.json'),struct('ready',true));
    inbox=fullfile(folder,'inbox.json'); previous='';
    while ~isfile(fullfile(folder,'close.json'))
        if isfile(inbox)
            envelope=readJSON(inbox);
            if ~strcmp(previous,envelope.id)
                previous=envelope.id; current=envelope.runDir; done=false; revision=0;
                job=struct('config',config,'tools',specs,'messages',{messages},'prompt',string(envelope.prompt), ...
                    'systemPrompt',autoagent.systemPrompt(autoagent.Context.current(),config.enabledSkills));
                runner.start(job);
                writeJSON(fullfile(current,'accepted.json'),struct('accepted',true));
                while ~done, pause(0.1); end
            end
        end
        pause(0.1);
    end
catch err
    destination=folder; if ~isempty(current), destination=current; end
    writeJSON(fullfile(destination,'fatal.json'),struct('error',err.message));
end
if ~isempty(runner), delete(runner); end
if ~isempty(registry), delete(registry); end

    function update(type,data)
        revision=revision+1;
        if strcmp(type,'done')
            if isfield(data,'messages')
                messages=data.messages;
                writeJSON(fullfile(folder,'history.json'),struct('messages',{messages}));
            end
            writeJSON(fullfile(current,'result.json'),data); done=true;
        elseif strcmp(type,'error')
            writeJSON(fullfile(current,'result.json'),struct('ok',false,'error',data.error)); done=true;
        else
            % Immutable numbered events preserve adjacent tool start/result updates.
            if strcmp(type,'progress') && isfield(data,'messages')
                data=rmfield(data,'messages'); % Native history stays with the runner.
            end
            writeJSON(fullfile(current,sprintf('event-%010d.json',revision)),struct('revision',revision,'phase',type,'data',data));
        end
    end
    function reply=tool(req)
        if startsWith(string(req.name),'teams_')
            answer=exchange('collaboration',req);
            reply=struct('approved',true,'result',answer.result); return;
        end
        [automatic,category]=autoagent.Permissions.allows(config,req);
        approved=automatic && strcmp(category,'readOnly');
        if ~approved, answer=exchange('approval',req); approved=answer.approved; end
        reply=struct('approved',approved,'result','{"error":"user_denied"}');
        if ~approved, return; end
        if req.remote, reply.result='Approved'; return; end
        t=select(registry.Tools,string(req.name)); value=evaluate(t,req.arguments);
        if ~ischar(value) && ~isstring(value), value=jsonencode(value); end
        reply.result=char(string(value));
    end
    function answer=exchange(kind,req)
        id=char(java.util.UUID.randomUUID());
        writeJSON(fullfile(current,['call-' id '.json']),struct('id',id,'kind',kind,'name',req.name,'arguments',req.arguments));
        response=fullfile(current,['reply-' id '.json']); started=tic;
        while ~isfile(response)
            if toc(started)>600, error('Teams:Timeout','等待宿主回复超时'); end
            pause(0.1);
        end
        answer=readJSON(response);
    end
end
function value=readJSON(p)
value=jsondecode(fileread(p));
end
function writeJSON(p,value)
tmp=[p '.tmp']; fid=fopen(tmp,'w','n','UTF-8');
assert(fid>=0,'Teams:IO','Cannot write %s',tmp);
fwrite(fid,unicode2native(jsonencode(value),'UTF-8'),'uint8'); fclose(fid);
movefile(tmp,p,'f');
end
