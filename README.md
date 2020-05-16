# Finally, a qt encoder

qencoder is the gui you never knew you needed. With the power of scene-based splitting, it's now faster and easier than ever to encode with free codecs. Make the perfect video encodes with qencoder!

### Simple and easy to use
![Simple view](/screenshots/simple.png)

You don't need to have a deep understanding of how video works to take advantage of qencoder. With extremely easy to use and powerful presets, qencoder is for everyone.


### Powerful for those who need it
![Advanced view](/screenshots/complex.png)

qencoder features many useful features which make it a powerful tool. With scene based splitting, qencoder is the first ever gui to take advantage of systems with hundreds of cores. By splitting at the right moments, qencoder ensures your videos do not have any overhead from unneeded keyframes.

It also is the first gui capable of boosting dark scenes. Allowing you to use lower q values to avoid nasty artifacts like banding when needed.

It allows you to configure the colorspace of both your input and output, to ensure that your hdr video stays hdr.

Finally, it supports minimal splitting, the ideal mode for 2 pass vbr encodes. This mode makes as few splits as possible, keeping them all as far apart as possible so that the bitrate stays as variable as possible.

### Video queueing

![Queue view](/screenshots/queue.png)

qencoder is the first gui av1 encoder to support proper video queueing. Setup the perfect encode for your video and add it to a queue. Repeat for as many videos as you want to encode. When you are done, save the queue to a file for later, or run it now with the encode button. If any videos are in the queue, qencoder will encode them.

### The optimal encodes

qencoder takes advantage of the most modern and advanced free formats. Including:

aomenc's av1, a video codec so efficient it can achieve better than dvd quality in less space than a CD. Aomenc paired with a splitting tool like qencoder is the fastest and most efficient way to encode av1, better than even SVT or rav1e.

Libvpx vp9/8. Video codecs which have become standard across the internet in the .webm video format, as well as commonly being used for game cutscenes.

### Free codecs

qencoder supports free codecs that can be encoded into webm. This means your videos can be shared and played on any html5 compliant browser. It also means that you do not need to worry about licensing fees or patent violation using it. Your encodes are yours, and should stay that way.

### Using qencoder

##### Windows

Download the latest 7zip in the "releases" section.

##### Linux

###### Ubuntu:

Via pip:

First, install ffmpeg, an up to date version of aomenc, and an up to date version of vpxenc. Then install qencoder.
```
sudo apt update
sudo apt install python-pip vpx-tools aom-tools ffmpeg
pip install qencoder
```

###### Arch:

It's recommended that you install it from the aur:

https://aur.archlinux.org/packages/qencoder/

###### Others/Manual installation:

Git clone this repository:

```git clone https://github.com/natis1/qencoder```

```cd qencoder```

Then install ffmpeg and an up-to-date version of the aom encoder (for instance aomenc-git, on arch)

Then install the python requirements:

```pip install -r requirements.txt```

Then run it with

```./qenc.py```

##### Legal note

app.ico modified from Wikimedia Commons by Videoplasty.com, CC-BY-SA 4.0
