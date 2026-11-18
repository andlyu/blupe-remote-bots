"""Build the Sites ESM artifact from the public canonical integration source."""
from pathlib import Path
import argparse,json,shutil
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--project-id',required=True);args=p.parse_args()
root=Path(__file__).resolve().parents[1];out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
(out/'worker').mkdir(exist_ok=True);(out/'dist/server').mkdir(parents=True,exist_ok=True);(out/'.openai').mkdir(exist_ok=True)
page=json.dumps((root/'site/page.html').read_text());source=(root/'site/worker.js').read_text().replace("import {PAGE} from './page.js';",'const PAGE = '+page+';')
(out/'worker/index.js').write_text(source);(out/'dist/server/index.js').write_text(source)
(out/'.openai/hosting.json').write_text(json.dumps({'project_id':args.project_id},indent=2)+'\n')
(out/'dist/.openai').mkdir(exist_ok=True);shutil.copyfile(out/'.openai/hosting.json',out/'dist/.openai/hosting.json')
(out/'package.json').write_text(json.dumps({'name':'gemini-blupe','private':True,'type':'module','scripts':{'check':'node --check worker/index.js'}},indent=2)+'\n')
(out/'.gitignore').write_text('node_modules/\n.sites-runtime/\n.env*\n')
(out/'README.md').write_text('# Gemini\n\nBuilt from the canonical public BluPe integration under codex-runner/integrations/gemini-blupe. Runtime secrets are configured with Sites. This artifact contains no robot/model credentials. Physical acceptance remains pending.\n')
print(json.dumps({'output':str(out),'worker_bytes':len(source.encode())}))
