# Upstream information

As I pledged the iCopy-X Kickstarter and bought one iCopy-XS, in parallel to my [tear down efforts](https://github.com/iCopy-X-Community/icopyx-teardown),
I requested the vendor to honor the open source license of the Proxmark3 schematics and software and to share their modifications.

I will post here what I'll get and in parallel I'll try to create source repositories to enable some community development on it. Depending on what we'll get...

## Hardware

* [Schematics & Gerber of the green PCB](https://github.com/Nikola-Lab/icopy_hw_main_pcb)
* [Schematics & Gerber of the antenna PCB](https://github.com/Nikola-Lab/icopy_hw_ant_pcb)
* [Schematics & Gerber of the FPC connecting green PCB & Nanopi NEO](https://github.com/Nikola-Lab/icopy_hw_usb_fpc)



A [previous version of the main PCB schematics](https://github.com/Nikola-Lab/icopy_hw_main_pcb/blob/bb14741874880ff248141fc57d71e8be8f2f4c7b/SCH/ICOPY-X_V1.5.pdf)
contained PDF JavaScript pop-ups (visible only with Acrobat) from which we could extract the BoM.
Beware quantities and references are not present.

```
sudo apt install qpdf uni2ascii
qpdf -qdf ICOPY-X_V1.5.pdf ICOPY-X_V1.5q.pdf
sed -n '/popUp/s/.*popUpMenu\\(\([^;]*\)\\);.*/\1/p' ICOPY-X_V1.5q.pdf|sed 's/\\\\/\\/g;s/\\\([()]\)/\1/g'|ascii2uni -a U -q|sort|uniq > bom.txt
python3 bomtxt2csv.py
```

Using [bomtxt2csv.py](hw/bomtxt2csv.py). Then converting the `.csv` into `.ods` with LibreOffice -> [bom.ods](hw/bom.ods)

Note that current upstream contains now the [BOM of the main PCB](https://github.com/Nikola-Lab/icopy_hw_main_pcb/tree/main/BOM).

## FPGA

* [FPGA upstream code](https://github.com/Nikola-Lab/icopy_fpga_3s_0921)
  * See [diff](fpga/icopyx-fpga.diff) to compare Verilog files with FPGA code from Proxmark3
* A document in Chinese details these changes, cf [fpga](fpga) subdirectory with also a Google translated version.
* [Community fork](https://github.com/iCopy-X-Community/icopyx-community-fpga) with some cleaning & linux compilation script
  * Community fork version **is now merged in Proxmark3/RRG repo** in [fpga-xc3s100e](https://github.com/RfidResearchGroup/proxmark3/tree/master/fpga-xc3s100e) subdir.
## STM32

* [STM32 firmware](https://github.com/Nikola-Lab/icopy_stm32)
  * open source license: MIT
  * untested

## STM32 tools

* [icopy_time_synchronizer](https://github.com/Nikola-Lab/icopy_time_synchronizer), a tool to setup the STM32 RTC from the host(?)
  * open source license: MIT
  * untested
* [CSerialPort](https://github.com/Nikola-Lab/CSerialPort), fork of a serial library, used by icopy_time_synchronizer
  * open source license: LGPL
## Proxmark3

* [Proxmark3 upstream code snapshot](proxmark3/2021-07-02-09-41-01-766.zip)
  * They shared both the original repo at the point they cloned it and their sources. I removed the unnecessary original repo copy from the zip.
  * They forked at 29c8b3aa4ee8cb3d66a1542d95740d996abe201f and removed the `fpga/` as there is a separate repository for FPGA, see previous point.
  * See [diff](proxmark3/2021-07-02-09-41-01-766.diff) to compare with Proxmark3/RRG.
  * See [cleaned diff](proxmark3/2021-07-02-09-41-01-766-cleaned.diff) for a less noisy diff.
* [Community fork](https://github.com/iCopy-X-Community/icopyx-community-pm3)
  * branch `upstream` reflects the upstream code snapshot, but as commit on top of the Proxmark3/RRG history, from the forking point (tagged `icopyx-fork`).
  * branch `master` reverts a few unneeded changes.
  * Community fork version **is now merged in Proxmark3/RRG repo** as a set of commits, see [here](https://github.com/RfidResearchGroup/proxmark3/commit/ca2fcecfb94ad8b9cc049a30df9b59ce2a8a409f) and its previous commits.
## Python GUI

* Still missing, few elements disclosed in [lib](lib) subdir.
* Few community tests based on these elements [here](https://github.com/iCopy-X-Community/icopyx-community-tests).
## Timeline:

* 2021-07-01 Received hardware schematics
* 2021-07-02 Received reference to FPGA repository on Gitee and a Chinese document about the changes
* 2021-07-02 Received proxmark3 sources
* 2021-08-24 New vendor repos on Github
