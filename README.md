# FermiBadgerPlugins - Use Badger to run Xopt at Fermilab
Use this repo is one of two ways:

## 1. Install and run by hand:
```bash
git clone git@github.com:fermi-ad/FermiBadgerPlugins.git
cd FermiBadgerPlugins
conda create -n badger-env python=3.12.1 badger-opt=1.4.4 -y
conda activate badger-env 
pip install "acsys[settings]"==0.12.8 --extra-index-url https://www-bd.fnal.gov/pip3 --no-cache-dir
pip install xsuite
# Modify the four "..._ROOT" directories in the config.yaml file.  See notes.
badger -g -cf config.yaml
```
*Nota Bene* ```pip install``` of ```acsys-python``` requires being on the FNAL private network or active VPN thereto.

First-time startup notes:
1. Edit the ```*_ROOT``` directories in the config.yaml:
* ```BADGER_ARCHIVE_ROOT``` and ```BADGER_LOGBOOK_ROOT``` should be some location capacious enough for accumulating some data and logging histories. They can be the same value.
* ```BADGER_PLUGIN_ROOT``` and ```BADGER_TEMPLATE_ROOT``` can be set to the ```plugins``` directory of the cloned repository you are in now.
2. UNCHECK THE Automatic VARIABLES CHECKBOX before doing anything else on the GUI. A bug needs to be addressed.
3. Load the template "TuneQx.yaml" to see a quick-start example using the SimpleVirtualAccelerator Environment. "TuneQxQy_mobo.yaml" adjusts both quad busses to achieve setpoints in both transverse tunes.  For both of these setpoints see the Parameters of the environment. 

Detailed [use guide]([url](https://github.com/xopt-org/Badger/blob/2dfcfd06dbf420c002cbe6c0a47160d35236edec/GUI_GUIDE.md)) to the Badger GUI.

*On the EAF* remember to set ```export OMP_NUM_THREADS=8``` to prevent slow performance from thread flail. 

## 2. or Build a container image for running with Docker or podman
 - To build: (may require changes to your Docker descktop for sufficient RAM or other memory resources)
```bash
    cd root-of-this-repo/
    docker build -t adregistry.fnal.gov/ml-autotune/testimage:latest --platform linux/amd64 .
    docker login -u $USER adregistry.fnal.gov
    ## Services password ##
    docker push  adregistry.fnal.gov/ml-autotune/testimage:latest  
```

- To run 
```bash
    docker run --rm docker run --rm -v .:/app testimage:latest 
```
- To run your script directly without rebuilding the image:
```bash
   docker run --rm -v .:/app testimage:latest 
```
