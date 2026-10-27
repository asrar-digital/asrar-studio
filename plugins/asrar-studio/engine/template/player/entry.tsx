import React from 'react';
import {createRoot} from 'react-dom/client';
import {Player, PlayerRef} from '@remotion/player';
import {Main, init, PALETTES, ITEM_TYPES} from '../src/Main';

/* المعاينة الحية: نفس قالب الرندر يشتغل بالمتصفح — أي تعديل يبان فوراً */
let root: any = null, ver = 0;
const ref = React.createRef<PlayerRef>();
(window as any).AsrarPlayer = {
  PALETTES, ITEM_TYPES,
  mount(el: HTMLElement, tl: any, asset: (p: string) => string) {
    (globalThis as any).__ASRAR_ASSET = asset;
    root = createRoot(el);
    this.update(tl);
  },
  update(tl: any) {
    init(tl); ver++;
    const dur = Math.max(30, Math.round((tl.total || 1) * 30));
    root.render(<Player ref={ref} component={Main} inputProps={{v: ver}} durationInFrames={dur} fps={30}
      compositionWidth={1080} compositionHeight={1920} style={{width: '100%', aspectRatio: '9 / 16', borderRadius: 16, overflow: 'hidden'}}
      controls clickToPlay spaceKeyToPlayOrPause />);
  },
  player: () => ref.current,
};
