import json
import pathlib
import sys
p = json.load(sys.stdin)
out = pathlib.Path('outputs')
out.mkdir(exist_ok=True)
(out / 'tomorrow_pitch.md').write_text(p['md'], encoding='utf-8')
(out / 'one_page_rp.md').write_text(p['rp'], encoding='utf-8')
print('WROTE outputs/tomorrow_pitch.md')
print('WROTE outputs/one_page_rp.md')
