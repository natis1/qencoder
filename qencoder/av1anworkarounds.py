from av1an.manager import Manager
from av1an.project import Project
from av1an.startup.setup import startup_check
import json

def get_default_args():
    return {'input': None, 'temp': None, 'output_file': None, 'mkvmerge': False, 'logging': None,
            'resume': False, 'keep': False, 'config': None, 'webm': False, 'chunk_method': None, 'scenes': None,
            'split_method': 'pyscene', 'extra_split': None, 'threshold': 35, 'min_scene_len': 60,
            'reuse_first_pass': False, 'passes': None, 'video_params': None, 'encoder': 'aom', 'workers': 0,
            'no_check': False, 'force': False, 'vvc_conf': None, 'ffmpeg': '', 'audio_params': '-c:a copy',
            'pix_format': 'yuv420p10le', 'vmaf': False, 'vmaf_path': None, 'vmaf_res': '1920x1080', 'n_threads': None,
            'target_quality': None, 'target_quality_method': 'per_shot', 'probes': 4, 'min_q': None, 'max_q': None,
            'vmaf_plots': False, 'probing_rate': 4, 'vmaf_filter': None, 'quiet': True}


def get_av1an_proj(args):
    return Project(args)


def get_av1an(proj):
    startup_check(proj)
    return Manager.Main(proj)


def run_av1an(manager):
    manager.run()


def merge_args(dictargs):
    args1 = get_default_args()
    for key in dictargs:
        args1[key] = dictargs[key]
    print(args1)
    return args1


def done_count(temp, resume):
    done_path = temp / 'done.json'
    if resume and done_path.exists():
        with open(done_path) as done_file:
            data = json.load(done_file)
        return sum(data['done'].values())
    else:
        return 0
