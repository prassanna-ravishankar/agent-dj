(
var projectRoot = PathName(thisProcess.nowExecutingPath).pathOnly.dirname;
var readyFile = (projectRoot +/+ "sessions" +/+ ".runtime-ready").standardizePath;
var pidFile = (projectRoot +/+ "sessions" +/+ ".runtime-pid").standardizePath;

s = Server.local;
s.options.sampleRate = 48000;
s.options.numOutputBusChannels = 2;
s.options.numInputBusChannels = 2;
s.options.memSize = 262144;

s.waitForBoot({
    (projectRoot +/+ "supercollider" +/+ "synthdefs" +/+ "core.scd").load;
    s.sync;

    ~deckA = Synth.head(s, \agentDjTone, [\out, 16, \freq, 440, \amp, 0.2]);
    ~deckB = Synth.after(~deckA, \agentDjTone, [\out, 18, \freq, 880, \amp, 0.2]);
    ~mixer = Synth.after(~deckB, \agentDjMixer, [\inA, 16, \inB, 18, \out, 20, \xfade, -1]);
    ~master = Synth.after(~mixer, \agentDjMaster, [\in, 20, \out, 0]);

    OSCdef(\agentDjSet, { |message|
        var parameter = message[1].asString.asSymbol;
        var value = message[2].asFloat;
        ~mixer.set(parameter, value);
    }, '/agent-dj/set');

    OSCdef(\agentDjCrossfade, { |message|
        ~mixer.set(\lag, message[2].asFloat.max(0.01));
        ~mixer.set(\xfade, message[1].asFloat.clip(-1, 1));
    }, '/agent-dj/crossfade');

    OSCdef(\agentDjLoad, { |message|
        var deck = message[1].asString;
        var path = message[2].asString;
        Buffer.read(s, path, action: { |buffer|
            if(deck == "A", {
                ~deckA.free;
                if(~bufferA.notNil, { ~bufferA.free });
                ~bufferA = buffer;
                ~deckA = Synth.before(~mixer, \agentDjFile, [\out, 16, \bufnum, buffer]);
            }, {
                ~deckB.free;
                if(~bufferB.notNil, { ~bufferB.free });
                ~bufferB = buffer;
                ~deckB = Synth.before(~mixer, \agentDjFile, [\out, 18, \bufnum, buffer]);
            });
            ("AGENT_DJ_LOADED " ++ deck ++ " " ++ path).postln;
        });
    }, '/agent-dj/load');

    OSCdef(\agentDjRecord, { |message|
        var action = message[1].asString;
        if(action == "start", {
            var path = message[2].asString;
            Routine({
                if(~recorder.notNil, {
                    ~recorder.free; ~recordBuffer.close; ~recordBuffer.free;
                });
                ~recordBuffer = Buffer.alloc(s, 65536, 2);
                ~recordBuffer.write(path, "wav", "float", 0, 0, true);
                s.sync;
                ~recorder = Synth.after(
                    ~mixer, \agentDjRecorder, [\in, 20, \bufnum, ~recordBuffer]
                );
                ("AGENT_DJ_RECORDING " ++ path).postln;
            }).play(SystemClock);
        }, {
            if(~recorder.notNil, {
                ~recorder.free; ~recorder = nil;
                ~recordBuffer.close; ~recordBuffer.free; ~recordBuffer = nil;
            });
        });
    }, '/agent-dj/record');

    OSCdef(\agentDjQuit, {
        File.delete(readyFile);
        File.delete(pidFile);
        s.quit;
        0.exit;
    }, '/agent-dj/quit');

    File.use(readyFile, "w", { |file| file.write("ready\n") });
    File.use(pidFile, "w", { |file| file.write(thisProcess.pid.asString ++ "\n") });
    "AGENT_DJ_READY".postln;
});

CmdPeriod.doOnce({
    File.delete(readyFile);
    File.delete(pidFile);
});
)
