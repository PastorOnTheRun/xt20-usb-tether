/* Cap12 leftover located-0: 0x2C52A00 .. 0x2C60000 (54784 bytes, RWX). */
MEMORY { ADDON (rwx) : ORIGIN = 0x2C52A00, LENGTH = 54784 }
SECTIONS {
  .text : {
    KEEP(*(.text.thunk))
    KEEP(*(.text*))
    *(.text)
  } > ADDON
  .rodata : { *(.rodata*) *(.rodata) } > ADDON
  .data : { *(.data*) *(.data) } > ADDON
  .bss : { *(.bss*) *(.bss) *(COMMON) } > ADDON
  PROVIDE(end = .);
}
