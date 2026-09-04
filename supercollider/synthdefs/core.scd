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

SynthDef(\agentDjMaster, { |in=20, out=0, monitorOut=26, amp=0.8|
    var signal = In.ar(in, 2) * Lag.kr(amp, 0.05);
    var limited = Limiter.ar(signal, 0.89, 0.01);
    Out.ar(out, limited);
    Out.ar(monitorOut, limited);
}).add;

SynthDef(\agentDjStreamGuard, {
    |fallbackIn=20, streamIn=22, out=24, streamEnabled=0, forceFallback=0,
      threshold=0.00003, recoverySeconds=2.0, failureSeconds=0.02,
      fadeInSeconds=0.05, fadeOutSeconds=0.03, lookaheadSeconds=0.12|
    var fallback = In.ar(fallbackIn, 2);
    var stream = In.ar(streamIn, 2);
    // Detect per-channel magnitude so anti-phase stereo cannot look like silence.
    var level = Amplitude.kr((stream[0].abs + stream[1].abs) * 0.5, 0.01, 0.1);
    var delayedStream = DelayN.ar(stream, 0.25, lookaheadSeconds.clip(0, 0.25));
    // Hysteresis prevents quiet musical material from chattering at the threshold.
    var detected = Schmidt.kr(level, threshold * 0.5, threshold);
    var eligible = detected * streamEnabled * (1 - forceFallback);
    var goodAge = Sweep.kr(HPZ1.kr(eligible).max(0), 1);
    var badAge = Sweep.kr(HPZ1.kr(detected).neg.max(0), 1);
    var recovered = eligible * (goodAge >= recoverySeconds);
    var failed = (1 - detected) * (badAge >= failureSeconds);
    // Qualification and audible transition are deliberately separate. A stream
    // can only enter after sustained good output, and disable/force always wins.
    var qualified = SetResetFF.kr(
        recovered,
        failed + (1 - streamEnabled) + forceFallback
    );
    var admitted = qualified * streamEnabled * (1 - forceFallback);
    var streamMix = LagUD.kr(admitted, fadeInSeconds, fadeOutSeconds).clip(0, 1);
    var output = XFade2.ar(fallback, delayedStream, streamMix.linlin(0, 1, -1, 1));
    SendReply.kr(
        Impulse.kr(4),
        '/agent-dj/stream-health',
        [level, streamMix, streamEnabled, forceFallback, detected, qualified]
    );
    Out.ar(out, output);
}).add;

SynthDef(\agentDjRecorder, { |in=20, bufnum=0|
    DiskOut.ar(bufnum, In.ar(in, 2));
}).add;
)
