# Upstream information

As I pledged the iCopy-X Kickstarter and bought one iCopy-XS, in parallel to my [tear down efforts](https://github.com/iCopy-X-Community/icopyx-teardown),
I requested the vendor to honor the open source license of the Proxmark3 schematics and software and to share their modifications.

I will post here what I'll get and in parallel I'll try to create source repositories to enable some community development on it. Depending on what we'll get...

Timeline:

* 2021-07-01 Received hardware schematics
  * Available in [hardware](hardware) subdirectory, working on it in https://github.com/iCopy-X-Community/icopyx-community-hw
* 2021-07-02 Received reference to FPGA repository (https://gitee.com/kombi/icopy_fpga_3s_0921)
  * Mirrored as upstream in https://github.com/iCopy-X-Community/icopyx-community-fpga
  * I created a diff in [fpga](fpga) subdirectory to compare Verilog files with FPGA code from Proxmark3
* 2021-07-02 Received proxmark3 sources
  * Available in [proxmark3](proxmark3) subdirectory, working on it in https://github.com/iCopy-X-Community/icopyx-community-pm3
  * They shared both the original repo at the point they cloned it and their sources. I removed the unneccesary original repo copy from the zip.
  * They forked at 29c8b3aa4ee8cb3d66a1542d95740d996abe201f and removed the `fpga/` as there is a separate repository for PFGA, see previous point.
  * I created a diff in [proxmark3](proxmark3) subdirectory to get an overview of their change besides `fpga/` removal.
