/** Local energy-based endpoint detector. Silence alone never submits a command. */
export class EndOfSpeech {
  private lastVoice=0;
  private voicedMs=0;
  private heardSpeech=false;
  private previous:number|null=null;
  private floor=.003;
  constructor(private pauseMs=1800,private noSpeechMs=10000){}
  sample(rms:number,elapsedMs:number):'listening'|'end'|'no-speech'{
    const dt=this.previous===null?0:Math.min(150,Math.max(0,elapsedMs-this.previous));
    this.previous=elapsedMs;
    const threshold=Math.max(.015,this.floor*3);
    if(rms>threshold){this.voicedMs+=dt;this.lastVoice=elapsedMs;if(this.voicedMs>=250)this.heardSpeech=true;}
    else {this.voicedMs=0;this.floor=this.floor*.98+Math.min(rms,.01)*.02;}
    if(this.heardSpeech&&elapsedMs-this.lastVoice>=this.pauseMs)return 'end';
    if(!this.heardSpeech&&elapsedMs>=this.noSpeechMs)return 'no-speech';
    return 'listening';
  }
}
