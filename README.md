# WanBlendr
WanBlendr: WAN load balancing on OpenWrt using nftables only (no iptables)

⚠️ WanBlendr is authored and maintained by me. Parts of the source are intentionally withheld for now because the project is undergoing active testing and validation.

# Complete Corresponding Source (CCS) for my OpenWrt-based firmware

**WAN Belndr**
Wan Blendr Multi WAN load balancing/failover on OpenWrt using nftables only (no iptables)

This repository provides the **Complete Corresponding Source (CCS)** for the OpenWrt-based images I distribute for the following devices:

- **rb750gr3**
- **rb5009**
- **RAISECOM_MSG1500 && Mercury KM08-708h 704 GAPM-7200**

⚠️ Based on OpenWrt (GPLv2). Not affiliated with or endorsed by the OpenWrt project.

The goal is to comply with free/open-source licenses (especially **GPLv2**) and to enable anyone to **reproduce the same images** from source.

---

## 💬 Join our Facebook Group
Have questions or want to share your experience with others?  
👉 [Join the Facebook Page](https://www.facebook.com/share/1ELjfY5Y1b/)

---

## What is included (per target)

- bsdtar
- irqbalance
- unzip
- micropython-mbedtls
- micropython-lib

Inside each target folder you will find:

- `configs/diffconfig` — the build configuration that matches the shipped image.
- `feeds.conf` — feed definitions used to fetch packages at build time.
- `files-public/` — public overlay files (e.g., default `/etc/config/*`) required to run the GPL components.
- `patches/` — any local patches I applied to OpenWrt or packages (if any).
- `scripts/build.sh` — a simple, reproducible build script.

There may also be `OPENWRT_COMMIT` and `OPENWRT_REMOTE` indicating the exact OpenWrt tree this build was based on (when applicable).

## What is NOT included (private MicroPython UI)
My **MicroPython-based web UI** and related private code are **not** included here.  
They are separate programs (mere aggregation) and are not derived from GPL code. Therefore, they are not part of the GPLv2 CCS requirement. The distributed commercial image contains that private UI; the publicly published CCS here contains everything required to rebuild the **OpenWrt base** and GPL-covered parts.

> If you rebuild using this CCS, you will get a functional OpenWrt-based image with the open-source components. You can add your own applications locally before building if desired.

## How to rebuild (quick start)
1. Install OpenWrt build prerequisites on your Linux host (gcc, g++, make, zlib, etc.).
2. Build host: Ubuntu 22.04.4 LTS jammy x86_64
3. Clone or unpack an OpenWrt buildroot matching the intended device and enter it, e.g.:
   ```bash
   
   sudo apt upgrade
   sudo apt update
   .
   sudo apt install build-essential clang flex bison g++ gawk \
   gcc-multilib g++-multilib gettext git libncurses5-dev libssl-dev \
   python3-setuptools rsync swig unzip zlib1g-dev file wget qemu-utils
   .
   git clone https://github.com/openwrt/openwrt.git openwrt
   cd openwrt
   git pull
   git tag
   git checkout v24.10.1
   git describe --tags
   v24.10.1
   ./scripts/feeds update -a
   ./scripts/feeds install -a
   make menuconfig
   Target System	 >  MediaTek Ralink MIPS (ramips)
   Sub-target	 >  MT7621 based boards
   Target Profile > RAISECOM_MSG1500 X.00
   ./scripts/feeds update -a
   ./scripts/feeds install bsdtar irqbalance unzip micropython-mbedtls micropython-lib
   ./scripts/feeds update -a
   ./scripts/feeds install -a

---


## Wan Blendr

   ```bash
   
	# WanBlendr v1.0
	# SPDX-License-Identifier: GPL-2.0-only
	# SPDX-FileCopyrightText: © 2025 Abdulkader Alrezej <abdulkader.alrezej@gmail.com> (Facebook: https://www.facebook.com/abdulkader.alrezej)
	
	config wanblendr 'globals'
		option lan_if 'p5'
		option interval '5'
		option retries_down '3'
		option retries_up '3'
		option buckets '100'
		option equalize_active '1'
	
	config wan 'wan1'
		option ifname 'wan1'
		option table '201'
		option mark '0xC9'
		option weight '50'
		option probe_ip '8.8.4.4'
	
	config wan 'wan2'
		option ifname 'wan2'
		option table '202'
		option mark '0xCA'
		option weight '50'
		option probe_ip '8.8.4.4'
	
	config policy
		option src '192.168.6.0/24'
		option wans 'wan2'

   ```


<img width="1546" height="840" alt="Test1_5009" src="https://github.com/user-attachments/assets/261eadc4-e8fa-43e5-8cd0-dc970d986aae" />
