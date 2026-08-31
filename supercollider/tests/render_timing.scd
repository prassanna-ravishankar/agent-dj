(
var projectRoot = PathName(thisProcess.nowExecutingPath).pathOnly.dirname.dirname;
var outputPath = "AGENT_DJ_RENDER".getenv;
s = Server.local;
s.options.sampleRate = 48000;
s.options.numOutputBusChannels = 2;
s.options.numInputBusChannels = 0;
s.waitForBoot({
    var deckA, deckB, mixer, recorder, buffer;
    (projectRoot +/+ "supercollider" +/+ "synthdefs" +/+ "core.scd").load;
    s.sync;
    buffer = Buffer.alloc(s, 65536, 2);
    buffer.write(outputPath, "wav", "float", 0, 0, true);
    s.sync;
    deckA = Synth.head(s, \agentDjTone, [\out, 16, \freq, 440]);
    deckB = Synth.after(deckA, \agentDjTone, [\out, 18, \freq, 880]);
    mixer = Synth.after(deckB, \agentDjMixer, [\inA, 16, \inB, 18, \out, 20, \xfade, -1, \lag, 0]);
    recorder = Synth.after(mixer, \agentDjRecorder, [\in, 20, \bufnum, buffer]);
    Routine({
        2.wait;
        mixer.set(\xfade, 1);
        1.wait;
        recorder.free; 0.2.wait; buffer.close; buffer.free;
        deckA.free; deckB.free; mixer.free; s.sync; s.quit; 0.exit;
    }).play(SystemClock);
});
)

