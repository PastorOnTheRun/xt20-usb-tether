# Red night screen addon (Cap12)

This is a standalone relocation of the X-T20 RED NIGHT SCREEN overlay into the
free RAM left at the end of official FujiMod Cap12 (`0x2C52A00`). It does not
include Cap12 or other FujiMod / x70view sources.

`addon.bin` is the already-linked payload (sha256 in the top-level README).
Rebuilding it is optional. You need `arm-none-eabi-gcc`:

```sh
arm-none-eabi-gcc -marm -mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=softfp \
  -Os -ffreestanding -fno-builtin -fno-pic -fno-pie -fno-stack-protector \
  -fno-unwind-tables -fno-asynchronous-unwind-tables -ffunction-sections \
  -fdata-sections -c -o night_addon.o night_addon.c
arm-none-eabi-gcc -marm -mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=softfp \
  -c -o thunk.o thunk.S
arm-none-eabi-gcc -marm -mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=softfp \
  -c -o cap12_abs.o cap12_abs.S
arm-none-eabi-gcc -nostdlib -T addon.ld -o addon.elf \
  night_addon.o thunk.o cap12_abs.o
arm-none-eabi-objcopy -O binary addon.elf addon.bin
```

Use `../splice_cap12.py` to splice this payload into an official Cap12
`FMPATCH.BIN` that you already have. Do not commit or publish official Cap12
binaries.
