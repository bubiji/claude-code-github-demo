;; 摘自 `wasm2wat Wasm.wasm` 的输出：导出函数 encrypt = func 24（原样截取，未改写）
;; 完整 wat 共 9269 行 / 232 KB，体积过大不入库；可用 `wasm2wat Wasm.wasm -o Wasm.wat` 从同目录 Wasm.wasm 一键重生成

  (func (;24;) (type 8) (param i32 i32) (result i32)
    (local i32 i32 i32 i32)
    global.get 0
    i32.const 1152
    i32.sub
    local.tee 2
    global.set 0
    block (result i32)  ;; label = @1
      block  ;; label = @2
        block  ;; label = @3
          local.get 0
          call 18
          local.tee 4
          i32.const -16
          i32.lt_u
          if  ;; label = @4
            block  ;; label = @5
              block  ;; label = @6
                local.get 4
                i32.const 11
                i32.ge_u
                if  ;; label = @7
                  local.get 4
                  i32.const 16
                  i32.add
                  i32.const -16
                  i32.and
                  local.tee 5
                  call 3
                  local.set 3
                  local.get 2
                  local.get 5
                  i32.const -2147483648
                  i32.or
                  i32.store offset=112
                  local.get 2
                  local.get 3
                  i32.store offset=104
                  local.get 2
                  local.get 4
                  i32.store offset=108
                  br 1 (;@6;)
                end
                local.get 2
                local.get 4
                i32.store8 offset=115
                local.get 2
                i32.const 104
                i32.add
                local.set 3
                local.get 4
                i32.eqz
                br_if 1 (;@5;)
              end
              local.get 3
              local.get 0
              local.get 4
              call 8
              drop
            end
            local.get 3
            local.get 4
            i32.add
            i32.const 0
            i32.store8
            local.get 1
            call 18
            local.tee 0
            i32.const -16
            i32.ge_u
            br_if 1 (;@3;)
            block  ;; label = @5
              block  ;; label = @6
                local.get 0
                i32.const 11
                i32.ge_u
                if  ;; label = @7
                  local.get 0
                  i32.const 16
                  i32.add
                  i32.const -16
                  i32.and
                  local.tee 4
                  call 3
                  local.set 3
                  local.get 2
                  local.get 4
                  i32.const -2147483648
                  i32.or
                  i32.store offset=96
                  local.get 2
                  local.get 3
                  i32.store offset=88
                  local.get 2
                  local.get 0
                  i32.store offset=92
                  br 1 (;@6;)
                end
                local.get 2
                local.get 0
                i32.store8 offset=99
                local.get 2
                i32.const 88
                i32.add
                local.set 3
                local.get 0
                i32.eqz
                br_if 1 (;@5;)
              end
              local.get 3
              local.get 1
              local.get 0
              call 8
              drop
            end
            local.get 0
            local.get 3
            i32.add
            i32.const 0
            i32.store8
            local.get 2
            i32.const 0
            i32.store offset=80
            local.get 2
            i64.const 0
            i64.store offset=72
            local.get 2
            i32.const 72
            i32.add
            local.get 2
            i32.const 104
            i32.add
            call 9
            block  ;; label = @5
              local.get 2
              i32.load offset=76
              local.tee 0
              local.get 2
              i32.load offset=80
              i32.ne
              if  ;; label = @6
                local.get 2
                local.get 0
                local.get 2
                i32.const 88
                i32.add
                call 16
                i32.const 12
                i32.add
                local.tee 0
                i32.store offset=76
                br 1 (;@5;)
              end
              local.get 2
              i32.const 72
              i32.add
              local.get 2
              i32.const 88
              i32.add
              call 9
              local.get 2
              i32.load offset=76
              local.set 0
            end
            i32.const 0
            local.set 3
            local.get 2
            i32.const 0
            i32.store offset=48
            local.get 2
            i64.const 0
            i64.store offset=40
            local.get 2
            i32.load offset=72
            local.tee 1
            local.get 0
            i32.eq
            br_if 2 (;@2;)
            loop  ;; label = @5
              local.get 2
              i32.const 40
              i32.add
              local.get 1
              i32.load
              local.get 1
              local.get 1
              i32.load8_u offset=11
              local.tee 0
              i32.const 24
              i32.shl
              i32.const 24
              i32.shr_s
              i32.const 0
              i32.lt_s
              local.tee 3
              select
              local.get 1
              i32.load offset=4
              local.get 0
              local.get 3
              select
              call 22
              local.get 2
              i32.load offset=76
              local.tee 0
              i32.const 12
              i32.sub
              local.get 1
              i32.ne
              if (result i32)  ;; label = @6
                local.get 2
                i32.const 40
                i32.add
                i32.const 44
                call 10
                local.get 2
                i32.load offset=76
              else
                local.get 0
              end
              local.get 1
              i32.const 12
              i32.add
              local.tee 1
              i32.ne
              br_if 0 (;@5;)
            end
            local.get 2
            i32.load offset=44
            local.set 3
            local.get 2
            i32.load8_u offset=51
            local.set 1
            local.get 2
            i32.const 40
            i32.add
            local.set 0
            local.get 2
            i32.load offset=40
            br 3 (;@1;)
          end
          call 6
          unreachable
        end
        call 6
        unreachable
      end
      local.get 2
      i32.const 40
      i32.add
      local.set 0
      i32.const 0
      local.set 1
      i32.const 0
    end
    local.set 4
    local.get 2
    i32.const -1009589776
    i32.store offset=212
    local.get 2
    i64.const 1167088121787636990
    i64.store offset=204 align=4
    local.get 2
    i64.const -1167088121787636991
    i64.store offset=196 align=4
    local.get 2
    i64.const 0
    i64.store offset=120
    local.get 2
    i32.const 0
    i32.store offset=128
    local.get 2
    i32.const 120
    i32.add
    local.get 4
    local.get 2
    i32.const 40
    i32.add
    local.get 1
    i32.const 24
    i32.shl
    i32.const 24
    i32.shr_s
    i32.const 0
    i32.lt_s
    local.tee 4
    select
    local.get 3
    local.get 1
    i32.const 255
    i32.and
    local.get 4
    select
    call 40
    local.get 2
    i32.const 56
    i32.add
    local.get 2
    i32.const 120
    i32.add
    call 27
    local.get 0
    i32.load8_s offset=11
    i32.const -1
    i32.le_s
    if  ;; label = @1
      local.get 2
      i32.load offset=40
      call 1
    end
    local.get 2
    i32.const 0
    i32.store offset=48
    local.get 2
    i64.const 0
    i64.store offset=40
    local.get 2
    i32.const 40
    i32.add
    local.get 2
    i32.const 56
    i32.add
    call 9
    block  ;; label = @1
      local.get 2
      i32.load offset=44
      local.tee 0
      local.get 2
      i32.load offset=48
      i32.ne
      if  ;; label = @2
        local.get 2
        local.get 0
        local.get 2
        i32.const 88
        i32.add
        call 16
        i32.const 12
        i32.add
        local.tee 0
        i32.store offset=44
        br 1 (;@1;)
      end
      local.get 2
      i32.const 40
      i32.add
      local.get 2
      i32.const 88
      i32.add
      call 9
      local.get 2
      i32.load offset=44
      local.set 0
    end
    i32.const 0
    local.set 3
    local.get 2
    i32.const 0
    i32.store offset=32
    local.get 2
    i64.const 0
    i64.store offset=24
    block (result i32)  ;; label = @1
      local.get 0
      local.get 2
      i32.load offset=40
      local.tee 1
      i32.ne
      if  ;; label = @2
        loop  ;; label = @3
          local.get 2
          i32.const 24
          i32.add
          local.get 1
          i32.load
          local.get 1
          local.get 1
          i32.load8_u offset=11
          local.tee 0
          i32.const 24
          i32.shl
          i32.const 24
          i32.shr_s
          i32.const 0
          i32.lt_s
          local.tee 3
          select
          local.get 1
          i32.load offset=4
          local.get 0
          local.get 3
          select
          call 22
          local.get 2
          i32.load offset=44
          local.tee 0
          i32.const 12
          i32.sub
          local.get 1
          i32.ne
          if (result i32)  ;; label = @4
            local.get 2
            i32.const 24
            i32.add
            i32.const 44
            call 10
            local.get 2
            i32.load offset=44
          else
            local.get 0
          end
          local.get 1
          i32.const 12
          i32.add
          local.tee 1
          i32.ne
          br_if 0 (;@3;)
        end
        local.get 2
        i32.load8_u offset=35
        local.set 3
        local.get 2
        i32.const 24
        i32.add
        br 1 (;@1;)
      end
      local.get 2
      i32.const 24
      i32.add
    end
    local.set 4
    local.get 2
    i32.const 120
    i32.add
    i32.const 4
    i32.or
    i32.const 1024
    i32.const 1024
    call 8
    drop
    local.get 2
    i32.const 2048
    i32.store offset=120
    block (result i32)  ;; label = @1
      local.get 3
      i32.const 24
      i32.shl
      i32.const 24
      i32.shr_s
      i32.const -1
      i32.le_s
      if  ;; label = @2
        local.get 2
        i32.load offset=28
        local.set 0
        local.get 2
        i32.load offset=24
        br 1 (;@1;)
      end
      local.get 3
      i32.const 255
      i32.and
      local.set 0
      local.get 2
      i32.const 24
      i32.add
    end
    local.set 1
    local.get 2
    local.get 0
    i32.store offset=1148
    local.get 2
    i32.const 8
    i32.add
    local.get 2
    i32.const 120
    i32.add
    local.get 1
    local.get 2
    i32.const 1148
    i32.add
    call 51
    local.get 2
    i32.const 8
    i32.add
    local.set 1
    local.get 2
    i32.load8_s offset=19
    i32.const -1
    i32.le_s
    if  ;; label = @1
      local.get 2
      i32.load offset=8
      local.tee 1
      call 1
    end
    local.get 4
    i32.load8_s offset=11
    i32.const -1
    i32.le_s
    if  ;; label = @1
      local.get 2
      i32.load offset=24
      call 1
    end
    local.get 2
    i32.load offset=40
    local.tee 4
    if  ;; label = @1
      block (result i32)  ;; label = @2
        local.get 4
        local.get 4
        local.get 2
        i32.load offset=44
        local.tee 3
        i32.eq
        br_if 0 (;@2;)
        drop
        loop  ;; label = @3
          local.get 3
          i32.const 12
          i32.sub
          local.set 0
          local.get 3
          i32.const 1
          i32.sub
          i32.load8_s
          i32.const -1
          i32.le_s
          if  ;; label = @4
            local.get 0
            i32.load
            call 1
          end
          local.get 0
          local.tee 3
          local.get 4
          i32.ne
          br_if 0 (;@3;)
        end
        local.get 2
        i32.load offset=40
      end
      local.set 0
      local.get 2
      local.get 4
      i32.store offset=44
      local.get 0
      call 1
    end
    local.get 2
    i32.load8_s offset=67
    i32.const -1
    i32.le_s
    if  ;; label = @1
      local.get 2
      i32.load offset=56
      call 1
    end
    local.get 2
    i32.load offset=72
    local.tee 4
    if  ;; label = @1
      block (result i32)  ;; label = @2
        local.get 4
        local.get 4
        local.get 2
        i32.load offset=76
        local.tee 3
        i32.eq
        br_if 0 (;@2;)
        drop
        loop  ;; label = @3
          local.get 3
          i32.const 12
          i32.sub
          local.set 0
          local.get 3
          i32.const 1
          i32.sub
          i32.load8_s
          i32.const -1
          i32.le_s
          if  ;; label = @4
            local.get 0
            i32.load
            call 1
          end
          local.get 0
          local.tee 3
          local.get 4
          i32.ne
          br_if 0 (;@3;)
        end
        local.get 2
        i32.load offset=72
      end
      local.set 0
      local.get 2
      local.get 4
      i32.store offset=76
      local.get 0
      call 1
    end
    local.get 2
    i32.load8_s offset=99
    i32.const -1
    i32.le_s
    if  ;; label = @1
      local.get 2
      i32.load offset=88
      call 1
    end
    local.get 2
    i32.load8_s offset=115
    i32.const -1
    i32.le_s
    if  ;; label = @1
      local.get 2
      i32.load offset=104
      call 1
    end
    local.get 2
    i32.const 1152
    i32.add
    global.set 0
    local.get 1)

;; ---- 模块的 import / export 段（原样截取）----
  (import "wasi_snapshot_preview1" "proc_exit" (func (;0;) (type 0)))
  (func (;1;) (type 0) (param i32)
  (export "memory" (memory 0))
  (export "encrypt" (func 24))
  (export "__indirect_function_table" (table 0))
  (export "_initialize" (func 12))
  (export "stackSave" (func 28))
  (export "stackRestore" (func 26))
  (export "stackAlloc" (func 25))
  (elem (;0;) (i32.const 1) func 14 12 17 15 46 44 43 42 17 15 23 23 39 31 34 37 15 33 35 36)
  (data (;0;) (i32.const 1196) ">\00\00\00?\00\00\00>\00\00\00>\00\00\00?\00\00\004\00\00\005\00\00\006\00\00\007\00\00\008\00\00\009\00\00\00:\00\00\00;\00\00\00<\00\00\00=")
  (data (;1;) (i32.const 1288) "\01\00\00\00\02\00\00\00\03\00\00\00\04\00\00\00\05\00\00\00\06\00\00\00\07\00\00\00\08\00\00\00\09\00\00\00\0a\00\00\00\0b\00\00\00\0c\00\00\00\0d\00\00\00\0e\00\00\00\0f\00\00\00\10\00\00\00\11\00\00\00\12\00\00\00\13\00\00\00\14\00\00\00\15\00\00\00\16\00\00\00\17\00\00\00\18\00\00\00\19")
  (data (;2;) (i32.const 1404) "?\00\00\00\00\00\00\00\1a\00\00\00\1b\00\00\00\1c\00\00\00\1d\00\00\00\1e\00\00\00\1f\00\00\00 \00\00\00!\00\00\00\22\00\00\00#\00\00\00$\00\00\00%\00\00\00&\00\00\00'\00\00\00(\00\00\00)\00\00\00*\00\00\00+\00\00\00,\00\00\00-\00\00\00.\00\00\00/\00\00\000\00\00\001\00\00\002\00\00\003")
  (data (;3;) (i32.const 2048) "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/")
  (data (;4;) (i32.const 2128) "0123456789abcdef\00allocator<T>::allocate(size_t n) 'n' exceeds maximum supported size\00basic_string\00allocator<T>::allocate(size_t n) 'n' exceeds maximum supported size\00vector\00std::exception\00\00\00\00\000\09\00\00\03\00\00\00\04\00\00\00\05\00\00\00St9exception\00\00\00\00\1c\0a\00\00 \09\00\00\00\00\00\00\5c\09\00\00\01\00\00\00\06\00\00\00\07\00\00\00St11logic_error\00D\0a\00\00L\09\00\000\09\00\00\00\00\00\00\90\09\00\00\01\00\00\00\08\00\00\00\07\00\00\00St12length_error\00\00\00\00D\0a\00\00|\09\00\00\5c\09\00\00St9type_info\00\00\00\00\1c\0a\00\00\9c\09\00\00N10__cxxabiv116__shim_type_infoE\00\00\00\00D\0a\00\00\b4\09\00\00\ac\09\00\00N10__cxxabiv117__class_type_infoE\00\00\00D\0a\00\00\e4\09\00\00\d8\09\00\00\00\00\00\00\08\0a\00\00\09\00\00\00\0a\00\00\00\0b\00\00\00\0c\00\00\00\0d\00\00\00\0e\00\00\00\0f\00\00\00\10\00\00\00\00\00\00\00\8c\0a\00\00\09\00\00\00\11\00\00\00\0b\00\00\00\0c\00\00\00\0d\00\00\00\12\00\00\00\13\00\00\00\14\00\00\00N10__cxxabiv120__si_class_type_infoE\00\00\00\00D\0a\00\00d\0a\00\00\08\0a")
  (data (;5;) (i32.const 2712) "\a0\0cP"))
