import {describe,it,expect} from 'vitest';
import {EndOfSpeech} from './EndOfSpeech';
import {speechText} from './speech';
describe('speech endpoint',()=>{
  it('ignores silence and eventually reports no speech',()=>{const d=new EndOfSpeech();for(let t=0;t<10000;t+=50)expect(d.sample(0,t)).toBe('listening');expect(d.sample(0,10000)).toBe('no-speech');});
  it('does not submit on a short hesitation; ends after the full pause',()=>{const d=new EndOfSpeech(1800);for(let t=0;t<=1000;t+=50)d.sample(.1,t);for(let t=1050;t<2000;t+=50)expect(d.sample(0,t)).toBe('listening');for(let t=2000;t<=2300;t+=50)d.sample(.1,t);expect(d.sample(0,4050)).toBe('listening');expect(d.sample(0,4100)).toBe('end');});
  it('isolated clicks are not speech',()=>{const d=new EndOfSpeech();for(let t=0;t<10000;t+=50)d.sample(t%1000===0?.1:0,t);expect(d.sample(0,10000)).toBe('no-speech');});
  it('honors a longer pause setting',()=>{const d=new EndOfSpeech(2500);for(let t=0;t<=1000;t+=50)d.sample(.1,t);expect(d.sample(0,2800)).toBe('listening');expect(d.sample(0,3500)).toBe('end');});
  it('cleans markdown for spoken output',()=>expect(speechText('## Привет **мир** [сайт](https://x.ru)')).toBe('Привет мир сайт'));
});
