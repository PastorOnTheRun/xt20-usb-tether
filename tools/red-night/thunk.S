.syntax unified
.section .text.thunk,"ax",%progbits
.arm
.global red_night_osd_hook_entry
.type red_night_osd_hook_entry, %function
red_night_osd_hook_entry:
    push {r0, r1, r2, r3}
    push {r4, lr}
    add r0, sp, #8
    bl red_night_osd_hook
    cmp r0, #0
    pop {r4, lr}
    ldrne r0, [sp]
    addne sp, sp, #16
    bxne lr
    pop {r0, r1, r2, r3}
    /* Cap12 already hooked this site; jump to its thunk (stock + Focal). */
    b cap12_vglib_thunk
.size red_night_osd_hook_entry, . - red_night_osd_hook_entry
