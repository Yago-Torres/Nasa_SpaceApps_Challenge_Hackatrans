#!/usr/bin/env python3
"""Import ABB issues with gh. Dry-run by default; optional explicit update of existing issues."""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

SOURCE = Path(__file__).with_name('issues.json')
LABEL_COLORS = {'roadmap':'5319e7','phase:F0':'0052cc','phase:F1':'0e8a16','phase:F2':'1d76db','phase:F3':'fbca04','phase:F4':'c2e0c6','lead:A':'bfe5bf','lead:B':'d4c5f9','lead:C':'f9d0c4','priority:P0':'b60205','priority:P1':'fbca04'}

def gh(*args):
    p=subprocess.run(['gh',*map(str,args)],capture_output=True,text=True)
    if p.returncode:
        raise RuntimeError('gh '+ ' '.join(map(str,args[:3])) +': '+p.stderr.strip())
    return p.stdout.strip()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo',required=True,help='OWNER/REPO')
    ap.add_argument('--apply',action='store_true',help='Apply changes (otherwise only print plan)')
    ap.add_argument('--update-existing',action='store_true',help='Also replace existing ABB Issue bodies with updated text')
    ap.add_argument('--remove-legacy-vote-label',action='store_true',help='Remove needs-vote from existing ABB Issues (requires --update-existing)')
    ap.add_argument('--limit',type=int,default=0)
    args=ap.parse_args()
    if not re.fullmatch(r'[\w.-]+/[\w.-]+',args.repo):ap.error('Expected OWNER/REPO')
    if args.limit<0:ap.error('--limit must be nonnegative')
    if args.remove_legacy_vote_label and not args.update_existing:ap.error('--remove-legacy-vote-label requires --update-existing')
    issues=json.loads(SOURCE.read_text())
    if args.limit:issues=issues[:args.limit]
    assert len({x['id'] for x in issues})==len(issues)
    old=json.loads(gh('issue','list','--repo',args.repo,'--state','all','--limit','1000','--json','title,number,url,labels'))
    existing={m.group(1):i for i in old if (m:=re.match(r'^\[(ABB-\d+)\]',i['title']))}
    creates=[i for i in issues if i['id'] not in existing]
    updates=[i for i in issues if i['id'] in existing] if args.update_existing else []
    print(f"Repo: {args.repo}. New: {len(creates)}; existing: {len(issues)-len(creates)}; to update: {len(updates)}")
    for i in creates:print(('CREATE ' if args.apply else 'WOULD CREATE ')+i['id']+' '+i['title'])
    for i in updates:print(('UPDATE ' if args.apply else 'WOULD UPDATE ')+i['id']+f" (#{existing[i['id']]['number']})")
    if not args.apply:return 0
    if not creates and not updates:
        print('Nothing to change.');return 0
    names={x['name'] for x in json.loads(gh('label','list','--repo',args.repo,'--limit','200','--json','name'))}
    for label,color in LABEL_COLORS.items():
        if label not in names:gh('label','create',label,'--repo',args.repo,'--color',color)
    for i in creates:
        labels=['roadmap',f"phase:{i['phase']}",f"lead:{i['lead']}",f"priority:{i['priority']}"]
        u=gh('issue','create','--repo',args.repo,'--title',f"[{i['id']}] {i['title']}",'--body',i['body'],'--label',','.join(labels))
        print('CREATED',u)
    for i in updates:
        issue=existing[i['id']]
        number=str(issue['number'])
        gh('issue','edit',number,'--repo',args.repo,'--title',f"[{i['id']}] {i['title']}",'--body',i['body'])
        if args.remove_legacy_vote_label and any(l.get('name')=='needs-vote' for l in issue.get('labels',[])):
            gh('issue','edit',number,'--repo',args.repo,'--remove-label','needs-vote')
        print('UPDATED',issue['url'])
    print(f"Complete: created {len(creates)}, updated {len(updates)}. No branches/PRs created.")
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (RuntimeError,OSError,ValueError,AssertionError) as e:
        print('ERROR:',e,file=sys.stderr);sys.exit(2)
