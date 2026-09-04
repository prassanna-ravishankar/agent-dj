(
var projectRoot = PathName(thisProcess.nowExecutingPath).pathOnly.dirname.dirname;
var outputPath = "AGENT_DJ_RENDER".getenv;
var assetsPath = "AGENT_DJ_MRT2_ASSETS".getenv;
var modelPath = "AGENT_DJ_MRT2_MODEL".getenv;
var duration = "AGENT_DJ_DURATION".getenv.asFloat;

s = Server.local;
s.options.sampleRate = 48000;
s.options.numOutputBusChannels = 2;
s.options.numInputBusChannels = 0;
s.options.memSize = 262144;

s.waitForBoot({
    var recordBuffer, recorder;

    (projectRoot +/+ "supercollider" +/+ "synthdefs" +/+ "core.scd").load;
    s.sync;
    ~mrt2Test = MRT2.new(s, 16);
    Routine({
        while({ ~mrt2Test.isRunning.not }, { 0.1.wait });

        // Model and asset loading may block this disposable test server. The
        // production runtime performs it only after its fallback graph is audible.
        ~mrt2Test.assets(assetsPath);
        s.sync;
        ~mrt2Test.model(modelPath);
        s.sync;
        ~mrt2Test.bufferSize(8192);
        ~mrt2Test.prompt(0, "warm minimal house, steady drums, deep bass", 1.0);

        // Text encoding and ring-buffer priming happen asynchronously.
        12.wait;
        recordBuffer = Buffer.alloc(s, 65536, 2);
        recordBuffer.write(outputPath, "wav", "float", 0, 0, true);
        s.sync;
        recorder = Synth.tail(s, \agentDjRecorder, [\in, 16, \bufnum, recordBuffer]);
        duration.wait;

        recorder.free;
        0.25.wait;
        recordBuffer.close;
        recordBuffer.free;
        ~mrt2Test.free;
        s.sync;
        s.quit;
        0.exit;
    }).play(SystemClock);
});
)
