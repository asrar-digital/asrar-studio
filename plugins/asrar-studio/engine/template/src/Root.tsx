import {Composition} from 'remotion';
import {Main} from './Main';
import tl from './timeline.json';
export const RemotionRoot: React.FC = () => (
  <Composition id="Main" component={Main} fps={30} width={1080} height={1920} durationInFrames={Math.max(30, Math.round((tl as any).total * 30))} />
);
