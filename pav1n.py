#!/usr/bin/env python3

import time
import socket
import sys
import os
import shutil
from distutils.spawn import find_executable
from ast import literal_eval
from psutil import virtual_memory
import argparse
from multiprocessing import Pool
import multiprocessing
import subprocess
from pathlib import Path
from typing import Optional

import cv2
import statistics

from scenedetect.video_manager import VideoManager
from scenedetect.scene_manager import SceneManager
from scenedetect.detectors import ContentDetector

from PyQt5.QtWidgets import QLabel, QProgressBar


if sys.version_info < (3, 7):
    print('Av1an requires at least Python 3.7 to run.')
    sys.exit()


class Av1an:

    def __init__(self, args):
        """Av1an - Python wrapper for AV1 encoders."""
        self.args = args
        #self.progressBarMini = progressBarMini
        #self.progressBarMain = progressBarMain
        #self.progressLabel = progressLabel
        self.scenes: Optional[Path] = None
        self.pyscene = ''
        self.logging = self.args.temp / 'log.log'
        self.FFMPEG = 'ffmpeg -y -hide_banner -loglevel error'
        self.pix_format = f'-pix_fmt {self.args.pix_format}'
        self.ffmpeg_pipe = f' {self.pix_format} -f yuv4mpegpipe - |'


    def log(self, info):
        """Default logging function, write to file."""
        with open(self.logging, 'a') as log:
            log.write(time.strftime('%X') + ' ' + info)

    def call_cmd(self, cmd, capture_output=False):
        """Calling system shell, if capture_output=True output string will be returned."""
        if capture_output:
            return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout

        with open(self.logging, 'a') as log:
            subprocess.run(cmd, shell=True, stdout=log, stderr=log)

    def setup(self, input_file: Path):
        """Creating temporally folders when needed."""

        # Make temporal directories, and remove them if already presented
        if self.args.temp.exists() and self.args.resume:
            pass
        else:
            if self.args.temp.is_dir():
                shutil.rmtree(self.args.temp)
            (self.args.temp / 'split').mkdir(parents=True)
            (self.args.temp / 'encode').mkdir()

        if self.logging is os.devnull:
            self.logging = self.args.temp / 'log.log'

    def extract_audio(self, input_vid: Path):
        """Extracting audio from source, transcoding if needed."""
        audio_file = self.args.temp / 'audio.mkv'
        if audio_file.exists():
            self.log('Reusing Audio File\n')
            return

        # Capture output to check if audio is present

        check = fr'{self.FFMPEG} -ss 0 -i "{input_vid}" -t 0 -vn -c:a copy -f null -'
        is_audio_here = len(self.call_cmd(check, capture_output=True)) == 0

        if is_audio_here:
            self.log(f'Audio processing\n'
                     f'Params: {self.args.audio_params}\n')
            cmd = f'{self.FFMPEG} -i "{input_vid}" -vn ' \
                  f'{self.args.audio_params} {audio_file}'
            self.call_cmd(cmd)

    def reduce_scenes(self, scenes):
        """Windows terminal can't handle more than ~600 scenes in length."""
        if len(scenes) > 600:
            scenes = scenes[::2]
            self.reduce_scenes(scenes)
        return scenes

    def scene_detect(self, video: Path):
        """Running scene detection on source video for segmenting."""
        # Skip scene detection if the user choosed to

        try:

            # PySceneDetect used split video by scenes and pass it to encoder
            # Optimal threshold settings 15-50
            video_manager = VideoManager([str(video)])
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=self.args.threshold))
            base_timecode = video_manager.get_base_timecode()

            # If stats file exists, load it.
            if self.scenes and self.scenes.exists():
                # Read stats from CSV file opened in read mode:
                with self.scenes.open() as stats_file:
                    stats = stats_file.read()
                    self.log('Using Saved Scenes\n')
                    return stats

            # Work on whole video
            video_manager.set_duration()

            # Set downscale factor to improve processing speed.
            video_manager.set_downscale_factor()

            # Start video_manager.
            video_manager.start()

            # Perform scene detection on video_manager.
            self.log(f'Starting scene detection Threshold: {self.args.threshold}\n')
            scene_manager.detect_scenes(frame_source=video_manager, show_progress=False)

            # Obtain list of detected scenes.
            scene_list = scene_manager.get_scene_list(base_timecode)
            # Like FrameTimecodes, each scene in the scene_list can be sorted if the
            # list of scenes becomes unsorted.

            self.log(f'Found scenes: {len(scene_list)}\n')

            scenes = [scene[0].get_timecode() for scene in scene_list]

            # Fix for windows character limit
            if sys.platform != 'linux':
                scenes = self.reduce_scenes(scenes)

            scenes = ','.join(scenes[1:])

            # We only write to the stats file if a save is required:
            if self.scenes:
                self.scenes.write_text(scenes)
            return scenes

        except Exception as e:
            self.log(f'Error in PySceneDetect: {e}\n')
            print(f'Error in PySceneDetect{e}\n')
            sys.exit()

    def split(self, video, timecodes):
        """Spliting video by timecodes, or just copying video."""
        if len(timecodes) == 0:
            self.log('Copying video for encode\n')
            cmd = f'{self.FFMPEG} -i "{video}" -map_metadata -1 -an -c copy -avoid_negative_ts 1 {self.args.temp / "split" / "0.mkv"}'
        else:
            self.log('Splitting video\n')
            cmd = f'{self.FFMPEG} -i "{video}" -map_metadata -1 -an -f segment -segment_times {timecodes} ' \
                  f'-c copy -avoid_negative_ts 1 {self.args.temp / "split" / "%04d.mkv"}'

        self.call_cmd(cmd)

    def frame_probe(self, source: Path):
        """Get frame count."""
        cmd = f'ffmpeg -hide_banner  -i "{source.absolute()}" -an  -map 0:v:0 -c:v copy -f null - '
        frames = (self.call_cmd(cmd, capture_output=True)).decode("utf-8")
        frames = int(frames[frames.rfind('frame=') + 6:frames.rfind('fps=')])
        return frames

    def frame_check(self, source: Path, encoded: Path):
        """Checking is source and encoded video framecounts match."""
        status_file = Path(self.args.temp / 'done.txt')

        s1, s2 = [self.frame_probe(i) for i in (source, encoded)]

        if s1 == s2:
            with status_file.open('a') as done:
                done.write(f'({s1}, "{source.name}"), ')
        else:
            print(f'Frame Count Differ for Source {source.name}: {s2}/{s1}')

    def get_video_queue(self, source_path: Path):
        """Returns sorted list of all videos that need to be encoded. Big first."""
        queue = [x for x in source_path.iterdir() if x.suffix == '.mkv']

        if self.args.resume:
            done_file = self.args.temp / 'done.txt'
            if done_file.exists():
                with open(done_file, 'r') as f:
                    data = [line for line in f]
                    data = literal_eval(data[-1])
                    queue = [x for x in queue if x.name not in [x[1] for x in data]]

        queue = sorted(queue, key=lambda x: -x.stat().st_size)

        if len(queue) == 0:
            print('Error: No files found in .temp/split, probably splitting not working')
            sys.exit()

        return queue

    def aom_encode(self, file_paths):
        """AOM encoding command composition."""

        two_p_1_aom = 'aomenc -q --passes=2 --pass=1'
        two_p_2_aom = 'aomenc  -q --passes=2 --pass=2'


        pass_2_commands = [
            (f'-i {file[0]} {self.ffmpeg_pipe}' +
             f' {two_p_1_aom} {self.args.video_params} --fpf={file[0].with_suffix(".log")} -o {os.devnull} - ',
             f'-i {file[0]} {self.ffmpeg_pipe}' +
             f' {two_p_2_aom} {self.args.video_params} --fpf={file[0].with_suffix(".log")} -o {file[1].with_suffix(".ivf")} - ',
             (file[0], file[1].with_suffix('.ivf')))
            for file in file_paths]
        return pass_2_commands

    def compose_encoding_queue(self, files):
        """Composing encoding queue with splitted videos."""
        file_paths = [(self.args.temp / "split" / file.name,
                       self.args.temp / "encode" / file.name,
                       file) for file in files]

        if self.args.encoder == 'aom':
            queue = self.aom_encode(file_paths)

        else:
            print(self.args.encoder)
            print(f'No valid encoder : "{self.args.encoder}"')
            sys.exit()

        self.log(f'Encoding Queue Composed\n'
                 f'Encoder: {self.args.encoder.upper()} Queue Size: {len(queue)} Passes: {self.args.passes}\n'
                 f'Params: {self.args.video_params}\n')

        return queue

    def get_brightness(self, video):
        """Getting average brightness value for single video."""
        brightness = []
        cap = cv2.VideoCapture(video)
        try:
            while True:
                # Capture frame-by-frame
                _, frame = cap.read()

                # Our operations on the frame come here
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # Display the resulting frame
                mean = cv2.mean(gray)
                brightness.append(mean[0])
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        except cv2.error:
            pass

        # When everything done, release the capture
        cap.release()
        brig_geom = round(statistics.geometric_mean([x+1 for x in brightness]), 1)

        return brig_geom

    def boost(self, command: str, br_geom, new_cq=0):
        """Based on average brightness of video decrease(boost) Quantizer value for encoding."""
        mt = '--cq-level='
        cq = int(command[command.find(mt) + 11:command.find(mt) + 13])
        if not new_cq:
            if br_geom < 128:
                new_cq = cq - round((128 - br_geom) / 128 * self.args.br)

                # Cap on boosting
                if new_cq < self.args.bl:
                    new_cq = self.args.bl
            else:
                new_cq = cq
        cmd = command[:command.find(mt) + 11] + \
              str(new_cq) + command[command.find(mt) + 13:]

        return cmd, new_cq

    def encode(self, commands):
        """Single encoder command queue and logging output."""
        # Passing encoding params to ffmpeg for encoding.
        # Replace ffmpeg with aom because ffmpeg aom doesn't work with parameters properly.

        st_time = time.time()
        source, target = Path(commands[-1][0]), Path(commands[-1][1])
        frame_probe_source = self.frame_probe(source)

        if self.args.boost:
            br = self.get_brightness(source.absolute().as_posix())

            com0, cq = self.boost(commands[0], br)

            if self.args.passes == 2:
                com1, _ = self.boost(commands[1], br, cq)
                commands = (com0, com1) + commands[2:]
            else:
                commands = com0 + commands[1:]

            boost = f'Avg brightness: {br}\nAdjusted CQ: {cq}\n'
        else:
            boost = ''

        self.log(f'Enc:  {source.name}, {frame_probe_source} fr\n{boost}\n')



        # Queue execution
        for i in commands[:-1]:
            print(rf'{self.FFMPEG} {i}')
            cmd = rf'{self.FFMPEG} {i}'
            self.call_cmd(cmd)

        self.frame_check(source, target)

        frame_probe = self.frame_probe(target)

        enc_time = round(time.time() - st_time, 2)

        self.log(f'Done: {source.name} Fr: {frame_probe}\n'
                 f'Fps: {round(frame_probe / enc_time, 4)} Time: {enc_time} sec.\n')
        return self.frame_probe(source)

    def concatenate_video(self, progressBarMini, progressBarMain, progressLabel):
        progressLabel.setText("Merging video...")
        progressBarMini.setValue(0)
        progressBarMini.setEnabled(0)
        progressBarMain.setValue(98)
        """With FFMPEG concatenate encoded segments into final file."""
        with open(f'{self.args.temp / "concat"}', 'w') as f:

            encode_files = sorted((self.args.temp / 'encode').iterdir())
            f.writelines(f"file '{file.absolute()}'\n" for file in encode_files)

        # Add the audio file if one was extracted from the input
        audio_file = self.args.temp / "audio.mkv"
        if audio_file.exists():
            audio = f'-i {audio_file} -c:a copy'
        else:
            audio = ''

        try:
            cmd = f'{self.FFMPEG} -f concat -safe 0 -i {self.args.temp / "concat"} {audio} -c copy -y "{self.args.output_file}"'
            concat = self.call_cmd(cmd, capture_output=True)
            if len(concat) > 0:
                raise Exception

            self.log('Concatenated\n')

            # Delete temp folders
            if not self.args.keep:
                shutil.rmtree(self.args.temp)

        except Exception as e:
            print(f'Concatenation failed, error: {e}')
            self.log(f'Concatenation failed, aborting, error: {e}\n')
            sys.exit()

    def encoding_loop(self, commands, progressBarMini, progressBarMain, progressLabel):
        """Creating process pool for encoders, creating progress bar."""
        with Pool(self.args.workers) as pool:

            self.args.workers = min(len(commands), self.args.workers)
            enc_path = self.args.temp / 'split'
            done_path = Path(self.args.temp / 'done.txt')
            if self.args.resume and done_path.exists():

                self.log('Resuming...\n')
                with open(done_path, 'r') as f:
                    lines = [line for line in f]
                    data = literal_eval(lines[-1])
                    total = int(lines[0])
                    done = [x[1] for x in data]

                self.log(f'Resumed with {len(done)} encoded clips done\n\n')

                initial = sum([int(x[0]) for x in data])

            else:
                initial = 0
                with open(Path(self.args.temp / 'done.txt'), 'w') as f:
                    total = self.frame_probe(self.args.file_path)
                    f.write(f'{total}\n')

            clips = len([x for x in enc_path.iterdir() if x.suffix == ".mkv"])
            print(f'\rQueue: {clips} Workers: {self.args.workers} Passes: {self.args.passes}\nParams: {self.args.video_params}')

            #bar = tqdm(total=total, initial=initial, dynamic_ncols=True, unit="fr",
            #           leave=False)
            progressLabel.setText(str(initial) + "/" + str(total))
            progressBarMini.setValue(int(100 * (initial / total)))
            progressBarMain.setValue(10 + int(85 * (initial / total)))

            loop = pool.imap_unordered(self.encode, commands)
            self.log(f'Started encoding queue with {self.args.workers} workers\n\n')

            try:
                for enc_frames in loop:
                    progressLabel.setText(str(enc_frames) + "/" + str(total))
                    progressBarMini.setValue(int(100 * (enc_frames / total)))
                    progressBarMain.setValue(5 + int(90 * (enc_frames / total)))
            except Exception as e:
                print(f'Encoding error: {e}')
                sys.exit()

    def setup_routine(self, progressBarMini, progressBarMain, progressLabel):
        """All pre encoding routine.
        Scene detection, splitting, audio extraction"""
        if not (self.args.resume and self.args.temp.exists()):
            # Check validity of request and create temp folders/files
            self.setup(self.args.file_path)


            # Splitting video and sorting big-first
            progressBarMain.setValue(1)
            progressLabel.setText("Scanning video...")
            timestamps = self.scene_detect(self.args.file_path)
            progressBarMain.setValue(5)
            progressLabel.setText("Splitting video...")
            self.split(self.args.file_path, timestamps)
            progressBarMain.setValue(8)

            progressLabel.setText("Extracting audio...")
            # Extracting audio
            self.extract_audio(self.args.file_path)
            progressBarMini.setEnabled(1)
            progressBarMain.setValue(10)
