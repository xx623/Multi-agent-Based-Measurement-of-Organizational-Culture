"""Deterministic input adapter only; it does not call or validate a language model."""
import argparse
import copy
import json
from pathlib import Path
import re

EVIDENCE_FIELDS=(
    'evidence_id','actor_role','reported_conduct','normative_language','activity_status',
    'temporal_status','reference_period','organizational_scope','qualifications','excerpts')

def nonblank(value, field):
    if not isinstance(value,str) or not value.strip():
        raise ValueError(field+' must be a nonblank string')
    return value

def restrict_record(reader_output):
    """Whitelist the revised Reader output; never pass through raw source/metadata."""
    input_id=nonblank(reader_output.get('input_id'),'input_id')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+',input_id):
        raise ValueError('Use an opaque input_id containing letters, digits, _, ., :, or -')
    record=reader_output.get('reader_agent')
    if not isinstance(record,dict):raise ValueError('reader_agent must be an object')
    if record.get('phase')!='revision':raise ValueError('Use the revised Reader output, not R1')
    evidence=record.get('evidence')
    flags=record.get('unresolved_flags')
    if not isinstance(evidence,list) or not isinstance(flags,list):
        raise ValueError('evidence and unresolved_flags must be arrays')
    restricted=[];ids=set()
    for item in evidence:
        if not isinstance(item,dict) or any(k not in item for k in EVIDENCE_FIELDS):
            raise ValueError('Evidence item lacks the Reader contract fields')
        kept={k:copy.deepcopy(item[k]) for k in EVIDENCE_FIELDS}
        for k in EVIDENCE_FIELDS:
            if k not in ('qualifications','excerpts'):nonblank(kept[k],k)
        eid=kept['evidence_id']
        if eid in ids:raise ValueError('Duplicate evidence_id: '+eid)
        ids.add(eid)
        if kept['activity_status'] not in ('completed','ongoing','planned','unspecified'):
            raise ValueError('Invalid activity_status')
        if kept['temporal_status'] not in ('implemented','planned','unknown'):
            raise ValueError('Invalid temporal_status')
        if kept['activity_status']=='planned' and kept['temporal_status']!='planned':
            raise ValueError('A planned action cannot be promoted to another channel')
        if kept['temporal_status']=='planned' and kept['activity_status']!='planned':
            raise ValueError('Planned channel requires planned activity_status')
        if not isinstance(kept['qualifications'],list):raise ValueError('qualifications must be an array')
        for q in kept['qualifications']:nonblank(q,'qualification')
        excerpts=kept['excerpts']
        if not isinstance(excerpts,list) or not excerpts:raise ValueError('Evidence needs source excerpts')
        kept['excerpts']=[{'source_ref':nonblank(x.get('source_ref'),'source_ref'),
                           'quote':nonblank(x.get('quote'),'quote')} for x in excerpts]
        restricted.append(kept)
    visible_flags=[];flag_ids=set()
    for flag in flags:
        if not isinstance(flag,dict):raise ValueError('Flag must be an object')
        fid=nonblank(flag.get('flag_id'),'flag_id')
        if fid in flag_ids:raise ValueError('Duplicate flag_id')
        flag_ids.add(fid)
        refs=flag.get('evidence_ids')
        if not isinstance(refs,list) or any(x not in ids for x in refs):
            raise ValueError('Flag references unknown evidence IDs; use [] for a missing item')
        # Exclude source_quote and other raw source fields from the flag view.
        visible_flags.append({'flag_id':fid,'evidence_ids':copy.deepcopy(refs),
                              'issue':nonblank(flag.get('issue'),'issue')})
    for item in restricted:
        if item['temporal_status']=='unknown':
            fid='AUTO_UNKNOWN_'+item['evidence_id']
            if fid not in flag_ids:
                visible_flags.append({'flag_id':fid,'evidence_ids':[item['evidence_id']],
                                      'issue':'Reference time is unknown; cannot support implemented or planned claims.'})
    return {'input_id':input_id,'evidence':restricted,'unresolved_flags':visible_flags}

def component_text(restricted_record):
    """All six unchanged templates receive this identical record serialization."""
    return ('Verified source-supported record for the current earnings-call component. '
            'No full narrative or declaration ledger is included.\n'
            +json.dumps(restricted_record,ensure_ascii=False,indent=2))

def render_specialist_prompt(template, restricted_record):
    values={'input_id':restricted_record['input_id'],'component_text':component_text(restricted_record)}
    placeholders=set(re.findall(r'\{\{([^{}]+)\}\}',template))
    if placeholders!={'input_id','component_text'}:
        raise ValueError('Unexpected placeholders in preserved specialist template')
    # One substitution pass: text inside a supplied value is never expanded again.
    return re.sub(r'\{\{([^{}]+)\}\}',lambda m:values[m.group(1)],template)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reader-output',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path)
    args=p.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        p.error('Choose a fresh output directory')
    record=restrict_record(json.loads(args.reader_output.read_text()))
    args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'verified_record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    (args.output_dir/'component_text.txt').write_text(component_text(record))
    root=Path(__file__).resolve().parent
    files=[f'agent{i}_{name}.txt' for i,name in enumerate(
        ['collaboration','customer','innovation','integrity','performance','miscellaneous'],1)]
    for name in files:
        template=(root/'prompts'/name).read_text(encoding='utf-8-sig')
        (args.output_dir/name).write_text(render_specialist_prompt(template,record))
    print(json.dumps({'status':'inputs_prepared_not_model_execution','specialist_inputs':len(files),
                      'output_dir':str(args.output_dir)}))

if __name__=='__main__':main()
