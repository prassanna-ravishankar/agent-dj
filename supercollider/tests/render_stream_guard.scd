(
var projectRoot = PathName(thisProcess.nowExecutingPath).pathOnly.dirname.dirname;
var outputPath = "AGENT_DJ_RENDER".getenv;
s = Server.local;
s.options.sampleRate = 48000;
s.options.numOutputBusChannels = 2;
s.options.numInputBusChannels = 0;
s.options.memSize = 262144;
s.waitForBoot({
    var fallback, stream, guard, master, recorder, buffer;
    (projectRoot +/+ "supercollider" +/+ "synthdefs" +/+ "core.scd").load;
    s.sync;
    buffer = Buffer.alloc(s, 65536, 2);
    buffer.write(outputPath, "wav", "float", 0, 0, true);
    s.sync;

    fallback = Synth.head(s, \agentDjTone, [\out, 20, \freq, 440, \amp, 0.2]);
    stream = Synth.after(fallback, \agentDjTone, [\out, 22, \freq, 880, \amp, 0.2]);
    guard = Synth.after(stream, \agentDjStreamGuard, [
        \fallbackIn, 20, \streamIn, 22, \out, 24,
        \streamEnabled, 0, \forceFallback, 0,
        \recoverySeconds, 2.0, \failureSeconds, 0.02,
        \fadeInSeconds, 0.05, \fadeOutSeconds, 0.03,
        \lookaheadSeconds, 0.2
    ]);
    master = Synth.after(guard, \agentDjMaster, [
        \in, 24, \out, 0, \monitorOut, 26
    ]);
    recorder = Synth.after(master, \agentDjRecorder, [\in, 26, \bufnum, buffer]);
    OSCdef(\agentDjGuardTestHealth, { |message|
        ("AGENT_DJ_GUARD_STATE " ++ message[3..].asString).postln;
    }, '/agent-dj/stream-health');

    Routine({
        0.5.wait;
        guard.set(\streamEnabled, 1);
        2.7.wait;
        // A shorter-than-failure-hold blip must not move the selector.
        stream.set(\amp, 0); 0.01.wait; stream.set(\amp, 0.2);
        0.59.wait;
        // Sustained generator silence must return to the fallback before the
        // delayed zero reaches the output.
        stream.set(\amp, 0);
        0.8.wait;
        stream.set(\amp, 0.2);
        2.6.wait;
        guard.set(\forceFallback, 1);
        0.8.wait;
        recorder.free; 0.2.wait; buffer.close; buffer.free;
        fallback.free; stream.free; guard.free; master.free;
        s.sync;
        "AGENT_DJ_STREAM_GUARD_RENDER_COMPLETE".postln;
        s.quit;
        0.exit;
    }).play(SystemClock);
});
)
