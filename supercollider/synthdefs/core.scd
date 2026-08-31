(
SynthDef(\agentDjTone, { |out=16, freq=440, amp=0.2|
    Out.ar(out, SinOsc.ar(freq, 0, amp) ! 2);
}).add;

SynthDef(\agentDjFile, { |out=16, bufnum=0, amp=1, rate=1|
    var signal = PlayBuf.ar(2, bufnum, BufRateScale.kr(bufnum) * rate, loop: 1);
    Out.ar(out, signal * amp);
}).add;

SynthDef(\agentDjMixer, {
    |inA=16, inB=18, out=20, xfade=(-1), gainA=1, gainB=1,
      lowpassA=20000, lowpassB=20000, highpassA=20, highpassB=20, lag=0.05|
    var a = In.ar(inA, 2) * Lag.kr(gainA, lag);
    var b = In.ar(inB, 2) * Lag.kr(gainB, lag);
    var position = Lag.kr(xfade, lag).clip(-1, 1);
    a = LPF.ar(HPF.ar(a, highpassA.clip(20, 18000)), lowpassA.clip(40, 20000));
    b = LPF.ar(HPF.ar(b, highpassB.clip(20, 18000)), lowpassB.clip(40, 20000));
    Out.ar(out, XFade2.ar(a, b, position));
}).add;

SynthDef(\agentDjMaster, { |in=20, out=0, amp=0.8|
    var signal = In.ar(in, 2) * Lag.kr(amp, 0.05);
    Out.ar(out, Limiter.ar(signal, 0.89, 0.01));
}).add;

SynthDef(\agentDjRecorder, { |in=20, bufnum=0|
    DiskOut.ar(bufnum, In.ar(in, 2));
}).add;
)

