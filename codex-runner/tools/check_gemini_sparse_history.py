"""Optional live no-motion probe. Only a synthetic acknowledge tool is declared.

Uses the actual sparse selector and raw native thought/tool history, never a
robot/session API. API acceptance is evidence, not a provider support guarantee.
"""
import argparse
import base64
import io
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from gemini_playground import load_api_key
from remote_yam.gemini_policy import GeminiAdapter
from remote_yam.gemini_context import RETAINED_CALL_AGES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Tiny synthetic image, three labelled views. No camera access.
    from PIL import Image
    image = io.BytesIO()
    Image.new('RGB', (32, 32), 'gray').save(image, format='JPEG')
    jpeg = 'data:image/jpeg;base64,' + base64.b64encode(image.getvalue()).decode()
    adapter = GeminiAdapter(load_api_key(args.env_file), timeout_s=60)
    tool = {'type':'function', 'name':'acknowledge', 'description':'Acknowledge a synthetic test sequence number. No action occurs.',
            'parameters':{'type':'object','properties':{'sequence':{'type':'integer'}},'required':['sequence']}}
    history = [{'role':'system','content':'This is a no-motion protocol test. Call acknowledge exactly once with the current sequence. Never request actions.'},
               {'role':'user','content':'Goal: verify sparse native tool history only.'}]
    receipt = {'model':adapter.model, 'retained_call_ages':list(RETAINED_CALL_AGES),
               'robot_access':False, 'documented_support':False, 'calls':[]}
    started = time.monotonic()
    for number in range(1, 13):
        content = [{'type':'input_text','text':f'Current synthetic sequence: {number}'}]
        for camera in ('top','left','right'):
            content.extend([{'type':'input_text','text':f'Camera: {camera}'}, {'type':'input_image','image_url':jpeg}])
        history.append({'role':'user','content':content})
        tick = time.monotonic()
        try:
            raw = adapter._post_json({'model':adapter.model, 'input':history, 'tools':[tool]})
            calls = [item for item in raw['output'] if item.get('type') == 'function_call']
            assert len(calls) == 1 and calls[0]['name'] == 'acknowledge'
            assert json.loads(calls[0]['arguments']) == {'sequence':number}
            history.extend(raw['output'])
            history.append({'type':'function_call_output','call_id':calls[0]['call_id'],
                            'output':json.dumps({'ok':True,'sequence':number,'action':'none'})})
            receipt['calls'].append({'number':number,'accepted':True,
                'selected_previous_calls':list(adapter._context.selected_calls),
                'native_thoughts':sum('_gemini_step' in item and item['_gemini_step']['type']=='thought' for item in raw['output']),
                'estimated_input_tokens':adapter._context.last_estimate,
                'usage':raw.get('usage',{}),'elapsed_s':round(time.monotonic()-tick,3)})
            print(f'Call {number}: accepted; retained {adapter._context.selected_calls}',flush=True)
        except Exception as exc:
            receipt['calls'].append({'number':number,'accepted':False,'error_type':type(exc).__name__})
            print(f'Call {number}: failed ({type(exc).__name__})',flush=True)
            break
        finally:
            receipt['elapsed_s'] = round(time.monotonic()-started,3)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(receipt,indent=2)+'\n')
    return 0 if len(receipt['calls']) == 12 and all(c['accepted'] for c in receipt['calls']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
