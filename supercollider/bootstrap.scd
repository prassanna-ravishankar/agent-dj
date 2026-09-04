(
var projectRoot = PathName(thisProcess.nowExecutingPath).pathOnly.dirname;
var readyFile = (projectRoot +/+ "sessions" +/+ ".runtime-ready").standardizePath;
var pidFile = (projectRoot +/+ "sessions" +/+ ".runtime-pid").standardizePath;
var streamStatusFile = (projectRoot +/+ "sessions" +/+ ".stream-status.json").standardizePath;
var mrt2Assets = "AGENT_DJ_MRT2_ASSETS".getenv;
var mrt2Model = "AGENT_DJ_MRT2_MODEL".getenv;
var mrt2Requested = "AGENT_DJ_MRT2_AVAILABLE".getenv == "1";
var mrt2Buffer = "AGENT_DJ_MRT2_BUFFER".getenv.asInteger.max(1920);
var mrt2Threshold = "AGENT_DJ_MRT2_THRESHOLD".getenv.asFloat.max(0.0000001);

s = Server.local;
s.options.sampleRate = 48000;
s.options.numOutputBusChannels = 2;
s.options.numInputBusChannels = 2;
s.options.memSize = 262144;

s.waitForBoot({
    var mrt2Class;
    (projectRoot +/+ "supercollider" +/+ "synthdefs" +/+ "core.scd").load;
    s.sync;

    ~deckA = Synth.head(s, \agentDjTone, [\out, 16, \freq, 440, \amp, 0.2]);
    ~deckB = Synth.after(~deckA, \agentDjTone, [\out, 18, \freq, 880, \amp, 0.2]);
    ~mixer = Synth.after(~deckB, \agentDjMixer, [\inA, 16, \inB, 18, \out, 20, \xfade, -1]);
    ~streamAvailable = false;
    ~streamPromptTexts = Array.fill(6, { "" });
    ~streamPromptWeights = Array.fill(6, { 0.0 });
    ~streamTemperature = 1.0;
    ~streamTopK = 40;

    ~streamGuard = Synth.after(~mixer, \agentDjStreamGuard, [
        \fallbackIn, 20, \streamIn, 22, \out, 24,
        \streamEnabled, 0, \forceFallback, 0, \threshold, mrt2Threshold
    ]);
    ~master = Synth.after(~streamGuard, \agentDjMaster, [
        \in, 24, \out, 0, \monitorOut, 26
    ]);

    OSCdef(\agentDjStreamHealth, { |message|
        var level = message[3].asFloat;
        var mix = message[4].asFloat;
        var enabled = message[5].asFloat > 0.5;
        var forced = message[6].asFloat > 0.5;
        var detected = message[7].asFloat > 0.5;
        var qualified = message[8].asFloat > 0.5;
        var healthy = enabled and: { qualified } and: { forced.not };
        var fallback = mix < 0.999;
        var streamActive = mix > 0.001;
        var warming = enabled and: { forced.not } and: { detected } and: { qualified.not };
        var phase = if(enabled.not, { "disabled" }, {
            if(forced, { "forced" }, {
                if(qualified, { "stream" }, {
                    if(warming, { "arming" }, { "fallback" })
                })
            })
        });
        File.use(streamStatusFile, "w", { |file|
            file.write(
                "{\"available\":%,\"enabled\":%,\"healthy\":%,\"fallback_active\":%,\"stream_active\":%,\"warming_up\":%,\"signal_detected\":%,\"phase\":\"%\",\"signal_level\":%,\"mix\":%}\n"
                .format(~streamAvailable, enabled, healthy, fallback, streamActive, warming, detected, phase, level, mix)
            );
        });
    }, '/agent-dj/stream-health');

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
                    ~master, \agentDjRecorder, [\in, 26, \bufnum, ~recordBuffer]
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

    OSCdef(\agentDjStreamPrompt, { |message|
        var slot = message[1].asInteger.clip(0, 5);
        var text = message[2].asString;
        var weight = message[3].asFloat.clip(0, 1);
        ~streamPromptTexts[slot] = text;
        ~streamPromptWeights[slot] = weight;
        if(~mrt2.notNil, { ~mrt2.prompt(slot, text, weight) });
    }, '/agent-dj/stream/prompt');

    OSCdef(\agentDjStreamWeight, { |message|
        var slot = message[1].asInteger.clip(0, 5);
        var target = message[2].asFloat.clip(0, 1);
        var seconds = message[3].asFloat.max(0);
        var start = ~streamPromptWeights[slot];
        var steps = (seconds * 20).ceil.asInteger.max(1);
        Routine({
            steps.do({ |index|
                var weight = start.blend(target, (index + 1) / steps);
                ~streamPromptWeights[slot] = weight;
                if(~mrt2.notNil, { ~mrt2.weight(slot, weight) });
                if(seconds > 0, { (seconds / steps).wait });
            });
        }).play(SystemClock);
    }, '/agent-dj/stream/weight');

    OSCdef(\agentDjStreamClear, { |message|
        var slot = message[1].asInteger.clip(0, 5);
        ~streamPromptTexts[slot] = "";
        ~streamPromptWeights[slot] = 0.0;
        if(~mrt2.notNil, { ~mrt2.clearPrompt(slot) });
    }, '/agent-dj/stream/clear');

    OSCdef(\agentDjStreamEnable, { |message|
        ~streamGuard.set(\streamEnabled, message[1].asInteger.clip(0, 1));
    }, '/agent-dj/stream/enable');

    OSCdef(\agentDjStreamFallback, { |message|
        ~streamGuard.set(\forceFallback, message[1].asInteger.clip(0, 1));
    }, '/agent-dj/stream/fallback');

    OSCdef(\agentDjStreamTemperature, { |message|
        ~streamTemperature = message[1].asFloat;
        if(~mrt2.notNil, { ~mrt2.temperature(~streamTemperature) });
    }, '/agent-dj/stream/temperature');

    OSCdef(\agentDjStreamTopK, { |message|
        ~streamTopK = message[1].asInteger;
        if(~mrt2.notNil, { ~mrt2.topk(~streamTopK) });
    }, '/agent-dj/stream/topk');

    OSCdef(\agentDjQuit, {
        File.delete(readyFile);
        File.delete(pidFile);
        File.delete(streamStatusFile);
        s.quit;
        0.exit;
    }, '/agent-dj/quit');

    File.use(readyFile, "w", { |file| file.write("ready\n") });
    File.use(pidFile, "w", { |file| file.write(thisProcess.pid.asString ++ "\n") });
    "AGENT_DJ_READY".postln;

    // The fallback graph is already audible and certified at this point. Resolve
    // and load the optional model afterwards so a missing, slow, or broken MRT2
    // installation cannot delay safe audio startup.
    Routine({
        mrt2Class = "MRT2".asSymbol.asClass;
        if(mrt2Requested and: { mrt2Class.notNil }, {
            try {
                ~mrt2 = mrt2Class.new(s, 22);
                while({ ~mrt2.isRunning.not }, { 0.1.wait });
                ~mrt2.assets(mrt2Assets);
                s.sync;
                ~mrt2.model(mrt2Model);
                s.sync;
                ~mrt2.bufferSize(mrt2Buffer);
                ~mrt2.temperature(~streamTemperature);
                ~mrt2.topk(~streamTopK);
                6.do({ |slot|
                    if(~streamPromptTexts[slot].isEmpty.not, {
                        ~mrt2.prompt(
                            slot,
                            ~streamPromptTexts[slot],
                            ~streamPromptWeights[slot]
                        );
                    });
                });
                ~streamAvailable = true;
                "AGENT_DJ_MRT2_READY".postln;
            } { |error|
                ~streamAvailable = false;
                ("AGENT_DJ_MRT2_FAILED " ++ error.asString).postln;
            };
        });
    }).play(SystemClock);
});

CmdPeriod.doOnce({
    File.delete(readyFile);
    File.delete(pidFile);
    File.delete(streamStatusFile);
});
)
