# WanBlendr & WanBlendrPlus-GPL-OpenWrt

WanBlendr is a WAN load balancing and failover firmware based on OpenWrt using nftables.

WanBlendr does not use mwan3 and does not use iptables.

This project is not affiliated with, sponsored by, or endorsed by the OpenWrt project.

## GPL Source

WanBlendr firmware is based on OpenWrt and includes GPL-covered and other open-source components.

For each firmware release, the matching CCS files are provided with the same GitHub Release as the firmware image.

Use the CCS files from the same release as the firmware image.

## What is NOT included (private MicroPython UI)
My MicroPython-based web UI and related private code are not included here.
They are separate programs (mere aggregation) and are not derived from GPL code. Therefore, they are not part of the GPLv2 CCS requirement. The distributed commercial image contains that private UI; the publicly published CCS here contains everything required to rebuild the OpenWrt base and GPL-covered parts.

## License

Files keep their respective licenses.

OpenWrt-derived and GPL-covered components are provided under their applicable open-source licenses.

See the included license notices and source files for details.
