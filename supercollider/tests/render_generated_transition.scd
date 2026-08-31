(
var projectRoot = PathName(thisProcess.nowExecutingPath).pathOnly.dirname.dirname;
var outputPath = "AGENT_DJ_RENDER".getenv;
var pathA = "AGENT_DJ_DECK_A".getenv;
var pathB = "AGENT_DJ_DECK_B".getenv;
var duration = "AGENT_DJ_DURATION".getenv.asFloat;
s = Server.local;
s.options.sampleRate = 48000;
s.options.numOutputBusChannels = 2;
s.options.numInputBusChannels = 0;
s.waitForBoot({
    var bufferA, bufferB, recordBuffer, deckA, deckB, mixer, recorder;
    (projectRoot +/+ "supercollider" +/+ "synthdefs" +/+ "core.scd").load;
    s.sync;
    bufferA = Buffer.read(s, pathA);
    bufferB = Buffer.read(s, pathB);
    recordBuffer = Buffer.alloc(s, 65536, 2);
    recordBuffer.write(outputPath, "wav", "float", 0, 0, true);
    s.sync;
    deckA = Synth.head(s, \agentDjFile, [\out, 16, \bufnum, bufferA]);
    deckB = Synth.after(deckA, \agentDjFile, [\out, 18, \bufnum, bufferB]);
    mixer = Synth.after(deckB, \agentDjMixer, [
        \inA, 16, \inB, 18, \out, 20, \xfade, -1, \lag, 0.25
    ]);
    recorder = Synth.after(mixer, \agentDjRecorder, [\in, 20, \bufnum, recordBuffer]);
    Routine({
        (duration * 0.35).wait;
        mixer.set(\xfade, 1);
        (duration * 0.65).wait;
        recorder.free; 0.2.wait;
        recordBuffer.close; recordBuffer.free;
        deckA.free; deckB.free; mixer.free; bufferA.free; bufferB.free;
        s.sync; s.quit; 0.exit;
    }).play(SystemClock);
});
)

