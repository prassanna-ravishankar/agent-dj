(
var projectRoot = PathName(thisProcess.nowExecutingPath).pathOnly.dirname.dirname;
var outputPath = "AGENT_DJ_RENDER".getenv;
var duration = ("AGENT_DJ_DURATION".getenv ? "8").asFloat;

if(outputPath.isNil, {
    "AGENT_DJ_RENDER must be set".postln;
    1.exit;
});

s = Server.local;
s.options.sampleRate = 48000;
s.options.numOutputBusChannels = 2;
s.options.numInputBusChannels = 0;
s.options.memSize = 262144;

s.waitForBoot({
    var deckA, deckB, mixer, recorder, buffer;
    (projectRoot +/+ "supercollider" +/+ "synthdefs" +/+ "core.scd").load;
    s.sync;

    buffer = Buffer.alloc(s, 65536, 2);
    buffer.write(outputPath, "wav", "float", 0, 0, true);
    s.sync;

    deckA = Synth.head(s, \agentDjTone, [\out, 16, \freq, 440, \amp, 0.2]);
    deckB = Synth.after(deckA, \agentDjTone, [\out, 18, \freq, 880, \amp, 0.2]);
    mixer = Synth.after(deckB, \agentDjMixer, [
        \inA, 16, \inB, 18, \out, 20, \xfade, -1, \lag, 0.75
    ]);
    recorder = Synth.after(mixer, \agentDjRecorder, [\in, 20, \bufnum, buffer]);

    Routine({
        2.wait;
        mixer.set(\xfade, 0);
        2.wait;
        mixer.set(\xfade, 1);
        2.wait;
        mixer.set(\gainB, 0.501187);
        1.wait;
        mixer.set(\lowpassB, 500);
        (duration - 7).max(0.1).wait;
        recorder.free;
        0.2.wait;
        buffer.close;
        buffer.free;
        deckA.free; deckB.free; mixer.free;
        s.sync;
        "AGENT_DJ_RENDER_COMPLETE".postln;
        s.quit;
        0.exit;
    }).play(SystemClock);
});
)

