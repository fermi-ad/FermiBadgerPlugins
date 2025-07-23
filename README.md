# FermiBadgerPlugins - Use Badger at Fermilab
From a clean conda environment:

```bash
conda create -n badger-env python=3.12.1 badger-opt==1.4.2
conda activate badger-env 
pip install "acsys[settings]"==0.12.8 --extra-index-url https://www-bd.fnal.gov/pip3 --no-cache-dir
git clone git@github.com:fermi-ad/FermiBadgerPlugins.git
cd FermiBadgerPlugins
badger -g
```
Upon first launch, may need to initialize.
Click the gear at the bottom right corner of the GUI, and set the PLUGIN_ROOT to the plugins directory in XoptBadgerTrial.
Quit Badger and re-launch.

<hr>
 OLD WAY:
```bash
conda create -n xopt-dev python=3.12.1 xopt
conda activate xopt-dev
conda install numpy=1.26.4
conda install badger-opt
pip install "acsys[settings]"==0.12.8 --extra-index-url https://www-bd.fnal.gov/pip3 --no-cache-dir
pip install requests
badger -g
```
python --version


## Use the ```plugins``` directory
Launch the GUI from the command line
```badger -g```
Then, from the gear menu (lower right corner), set the "Plugin Root" to the absolute path to the ```plugins/``` directory here in this repo. Now the GUI can access the interfaces and environments of this repo.
