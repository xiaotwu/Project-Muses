# P0 relink experiment notices

FFmpeg 8.0: exact release source archive is supplied in inputs/ffmpeg-8.0.tar.xz; selected configuration reports LGPL version 2.1 or later. The archive also contains optional code under other licenses; GPL/version3/nonfree components are disabled for this build. See FFmpeg-LICENSE.md and FFmpeg-COPYING.LGPLv2.1. Source: https://ffmpeg.org/releases/ffmpeg-8.0.tar.xz

miniaudio 0.11.26: exact header is supplied in inputs/miniaudio.h, with its complete license text. MIT No Attribution alternative selected. Source: https://github.com/mackron/miniaudio/tree/0.11.26

Original Muses P0 probe.cpp, backend.mm and p0_audio.h are marked MIT in their source. They are copied unchanged and supplied beside the frozen application objects. The two tone fixtures were generated for P0; no personal audio was used. Homebrew FFmpeg was used only in the earlier fixture-generation step, never linked into this prototype.

replacement.patch records the only intentional library-source modification: an observable av_version_info marker. This is not a decoder improvement, a library upgrade, or a legal determination about a product distribution. No production app, release, Developer ID identity or notarization was used.
