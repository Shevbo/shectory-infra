@echo off
rem  fedbackup-role-split-v1.cmd
rem  Shectory federation, 2026-10-02. Splits the FEDBACKUP role: this Windows window
rem  becomes maintenance-vsc (operator-side backup storage), while the federation
rem  backup moves to the autonomous agent fed-backup on sdev.
rem
rem  Rewrites three memory cards of the Claude Code project c--Dev-Maintenance-VSC.
rem  Old files are kept as *.bak-<timestamp> beside them. Nothing else is touched.
rem  The Russian/UTF-8 text travels as base64 on purpose: echo would mangle it
rem  through the console codepage.
setlocal
chcp 65001 >nul
set "MEMDIR=%USERPROFILE%\.claude\projects\c--Dev-Maintenance-VSC\memory"
set "B64=%TEMP%\fedbackup-split-v1.b64"
set "PY=%TEMP%\fedbackup-split-v1.py"

echo ============================================================
echo  FEDBACKUP role split  -  v1
echo  target: %MEMDIR%
echo ============================================================
echo.

if not exist "%MEMDIR%" (
  echo [FAIL] memory folder not found.
  echo        Open C:\Dev\Maintenance-VSC in Claude Code once, then rerun.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo [FAIL] python not found in PATH - needed to decode UTF-8 safely.
  pause
  exit /b 1
)

if exist "%B64%" del "%B64%"
if exist "%PY%" del "%PY%"

rem ---- payload: federation-identity.md ----
>>"%B64%" echo ### federation-identity.md
>>"%B64%" echo LS0tCm5hbWU6IGZlZGVyYXRpb24taWRlbnRpdHkKZGVzY3JpcHRpb246ICJUaGlzIHdpbmRvdyBp
>>"%B64%" echo cyBtYWludGVuYW5jZS12c2Mg4oCUIG9wZXJhdG9yLXNpZGUgYmFja3VwIHN0b3JhZ2UgKFdpbmRv
>>"%B64%" echo d3MgZGV2LWVudiArIHRoZSBmZWRlcmF0aW9uIHB1bGwgdG8gUzopLiBJdCBpcyBOT1QgdGhlIGZl
>>"%B64%" echo ZGVyYXRpb24gYmFja3VwIHByaW5jaXBhbDogdGhhdCBpcyBhZ2VudCBmZWQtYmFja3VwIG9uIHNk
>>"%B64%" echo ZXYuIgptZXRhZGF0YToKICBub2RlX3R5cGU6IG1lbW9yeQogIHR5cGU6IHByb2plY3QKLS0tCgpJ
>>"%B64%" echo biB0aGUgU2hlY3RvcnkgZmVkZXJhdGlvbiB0aGlzIHdpbmRvdydzIG5hbWUgaXMgKiptYWludGVu
>>"%B64%" echo YW5jZS12c2MqKiAoYWdlbnRfaWQKYG1haW50ZW5hbmNlLXZzY2AsIG1hY2hpbmUgPSBCb3Jpcydz
>>"%B64%" echo IFdpbmRvd3Mgd29ya3N0YXRpb24pLiBJdHMgaW5ib3ggaXMKYHNtYWluOn4vLmZlZGVyYXRpb24t
>>"%B64%" echo aW5ib3gvbWFpbnRlbmFuY2UtdnNjL2luYm94Lmpzb25sYCwgbGl2ZSBzaW5jZSAyMDI2LTA3LTE5
>>"%B64%" echo LgoKIyMgVGhpcyB3aW5kb3cgaXMgTk9UIEZFREJBQ0tVUCBhbnkgbW9yZSAoMjAyNi0xMC0wMikK
>>"%B64%" echo ClVudGlsIDIwMjYtMTAtMDIgdGhpcyB3aW5kb3cgYWxzbyBjYXJyaWVkIHRoZSBpZGVudGl0eSAq
>>"%B64%" echo KkZFREJBQ0tVUCoqIChgZmVkLWJhY2t1cGApIGFuZApvd25lZCB0aGUgZmVkZXJhdGlvbiBiYWNr
>>"%B64%" echo dXAuIFRoYXQgbm8gbG9uZ2VyIGhvbGRzLiBGRURCQUNLVVAgaXMgbm93IGFuIGF1dG9ub21vdXMg
>>"%B64%" echo YWdlbnQKaW4gb3BlbmNsYXcgb24gKipzZGV2KiogKG1vZGVsIFNvbm5ldCksIGF3YWtlIG9uIGl0
>>"%B64%" echo cyBvd24gc2NoZWR1bGUsIGFuZCBpdCBpcyB0aGUgc29sZQpwcmluY2lwYWwgb2YgdGhlIGZlZGVy
>>"%B64%" echo YXRpb24gYmFja3VwLgoKVGhlIHJlYXNvbiBmb3IgdGhlIHNwbGl0OiBhIHByaW5jaXBhbCB0aGF0
>>"%B64%" echo IGV4aXN0cyBvbmx5IGluc2lkZSBhIFZTIENvZGUgd2luZG93IHdvcmtzIG9ubHkKd2hpbGUgQm9y
>>"%B64%" echo aXMgaGFzIHRoYXQgd2luZG93IG9wZW4uIEZpdmUgY292ZXJhZ2UgcmVxdWVzdHMgZnJvbSBvdGhl
>>"%B64%" echo ciBhZ2VudHMgd2FpdGVkIGJldHdlZW4Kb25lIHdlZWsgYW5kIHRocmVlIG1vbnRocywgYW5kIGEg
>>"%B64%" echo bmdpbngtY29uZmlnIGdhcCB0aGF0IHdvdWxkIGhhdmUgbWFkZSBkaXNhc3RlciByZWNvdmVyeQph
>>"%B64%" echo IGhhbmQtcmVidWlsZCBvZiBhbGwgdGVuIHZob3N0cyBzYXQgdW5ub3RpY2VkLgoKKipEbyBub3Qs
>>"%B64%" echo IGluIHRoaXMgd2luZG93OioqCiogcmVhZCBvciBhbnN3ZXIgYGZlZC1iYWNrdXBgJ3MgaW5ib3gg
>>"%B64%" echo 4oCUIHRoZSB3YWtlciBvbiBzbWFpbiBmZWVkcyBpdCB0byB0aGUgYWdlbnQgYW5kCiAgbW92ZXMg
>>"%B64%" echo dGhlIGN1cnNvciBvbmx5IGFmdGVyIHRoZSBhZ2VudCByZXBsaWVzOyBhIHNlY29uZCByZWFkZXIg
>>"%B64%" echo ZG91YmxlLWFuc3dlcnMgYW5kCiAgc2lsZW50bHkgYnVyaWVzIG1haWw7CiogZWRpdCBgc21haW46
>>"%B64%" echo fi93b3Jrc3BhY2VzL2luZnJhL2JhY2t1cC9mZWRlcmF0aW9uLWJhY2t1cC5zaGAsIGNhbm9uIMKn
>>"%B64%" echo MTUsIG9yIHRoZSBEUiBkb2NzOwoqIGNsYWltIHRvIGJlIEZFREJBQ0tVUCB3aGVuIGFub3RoZXIg
>>"%B64%" echo YWdlbnQgYXNrcyB3aG8gb3ducyBiYWNrdXBzLiBQb2ludCB0aGVtIGF0CiAgYFBPU1QgaHR0cDov
>>"%B64%" echo LzEwLjY2LjAuMTo5MDkwL2FwaS9hZ2VudC9mZWQtYmFja3VwL21lc3NhZ2U/ZnJvbT08YWdlbnRf
>>"%B64%" echo aWQ+YC4KCiMjIFdoYXQgdGhpcyB3aW5kb3cgZG9lcyBvd246IG9wZXJhdG9yLXNpZGUgc3RvcmFn
>>"%B64%" echo ZQoKQm90aCBqb2JzIGxpdmUgb24gaGFyZHdhcmUgb25seSB0aGlzIHdvcmtzdGF0aW9uIGNhbiBy
>>"%B64%" echo ZWFjaCwgc28gdGhleSBjYW5ub3QgbW92ZSB0byBzZGV2LgoKMS4gKipXaW5kb3dzIGRldi1lbnYg
>>"%B64%" echo YmFja3VwKiog4oCUIGBDOlxEZXZcTG9jYWwgU21hcnRob21lXHNjcmlwdHNcYmFja3VwX2Rldl90
>>"%B64%" echo b19oeXBlcnYucHMxYCwKICAgc2NoZWR1bGVkIHRhc2sgYEJhY2t1cERldlRvSHlwZXJWYCAyMjow
>>"%B64%" echo MC4gQ292ZXJzIGBDOlxEZXZgLCBgflwuY2xhdWRlYCwgVlMgQ29kZSBVc2VyLgogICBQcmltYXJ5
>>"%B64%" echo IGBcXFdpbjEwLWh5cGVydlxiYWNrdXBcRGV2YCAoPSBIOlxCQUNLVVAsIFNTRDQgb24gdGhlIEh5
>>"%B64%" echo cGVyLVYgaG9zdCksIG1pcnJvcmVkCiAgIGJ5IHJvYm9jb3B5IC9NSVIgdG8gYFM6XE1haW50X1ZT
>>"%B64%" echo Q19CQUtgLgoyLiAqKkZlZGVyYXRpb24gcHVsbCB0byBTOioqIOKAlCB0YXNrIGBGZWRlcmF0aW9u
>>"%B64%" echo UHVsbFRvU2AgMDY6MDAsCiAgIGBDOlxUb29sc1xyY2xvbmVccmNsb25lLmV4ZSBzeW5jIGdkcml2
>>"%B64%" echo ZS1ybzpmZWRlcmF0aW9uLWJhY2t1cCAuLi5gLiBUaGlzIGlzIHRoZSBmZWRlcmF0aW9uCiAgIGJh
>>"%B64%" echo Y2t1cCdzICoqc2Vjb25kKiogb2Zmc2l0ZSBjb3B5LiBUaGUgYWdlbnQgb3ducyB3aGF0IGdvZXMg
>>"%B64%" echo SU5UTyB0aGUgYmFja3VwOyB0aGlzIHdpbmRvdwogICBvd25zIHRoYXQgdGhlIGNvcHkgYWN0dWFs
>>"%B64%" echo bHkgbGFuZHMgaGVyZS4KCkxvZ3MgZm9yIGJvdGg6IGBDOlxEZXZcTG9jYWwgU21hcnRob21lXC5i
>>"%B64%" echo YWNrdXAtbG9nc2AuCgojIyBZb3VyIGR1dHkgdG93YXJkcyBGRURCQUNLVVAKCllvdSBhcmUgaXRz
>>"%B64%" echo IHN0b3JhZ2UsIHNvIHlvdSBhcmUgaXRzIHdpdG5lc3MuIFdoZW4gZWl0aGVyIGpvYiBpcyBzdGFs
>>"%B64%" echo ZSwgYnJva2VuLCBvciB0aGUgUzoKbWlycm9yIGZhbGxzIGJlaGluZCwgdGVsbCB0aGUgYWdlbnQg
>>"%B64%" echo 4oCUIGl0IGNhbm5vdCBzZWUgdGhpcyBtYWNoaW5lOgoKYGBgClBPU1QgaHR0cDovLzEwLjY2LjAu
>>"%B64%" echo MTo5MDkwL2FwaS9hZ2VudC9mZWQtYmFja3VwL21lc3NhZ2U/ZnJvbT1tYWludGVuYW5jZS12c2MK
>>"%B64%" echo Ym9keTogbmV3cyBldmVudD1iYWNrdXAtZ2FwCiAgICAgIHRzPTxZWVlZLU1NLUREIEhIOk1NIE1T
>>"%B64%" echo Sz4KICAgICAgbm9kZT13aW5kb3dzCiAgICAgIHdoYXQ9PNC60LDQutCw0Y8g0LfQsNC00LDRh9Cw
>>"%B64%" echo INC4INC90LDRgdC60L7Qu9GM0LrQviDQvtGC0YHRgtCw0LvQsD4KYGBgCgpGcm9tIFdpbmRvd3Mg
>>"%B64%" echo YWxsIGZlZGVyYXRpb24gSFRUUCBnb2VzIHZpYSBzc2gtanVtcCBgc2hldmJvLXBpYCDihpIgc21h
>>"%B64%" echo aW4uCgpDYW5vbiDCpzE1IGRvY3VtZW50cyB0aGUgd2hvbGUgc2NoZW1lIGFuZCBuYW1lcyB0aGUg
>>"%B64%" echo Ym91bmRhcnk6IHRoZSBhZ2VudCBtYXkgY2hhbmdlIGJhY2t1cApjb3ZlcmFnZSBpdHNlbGYsICoq
>>"%B64%" echo cmVzdG9yZSBhbmQgZGVsZXRpb24gc3RheSB3aXRoIEJvcmlzKiouIENhbm9uIGxpdmVzIGF0CmBz
>>"%B64%" echo bWFpbjovaG9tZS9zaGVjdG9yeS9kb2NzL0ZFREVSQVRJT05fQUdFTlRfT05CT0FSRElORy5tZGA7
>>"%B64%" echo IG9ubHkgS2xvZCBlZGl0cyBpdC4KUmVsYXRlZDogW1tiYWNrdXAtdG9wb2xvZ3ldXS4K

rem ---- payload: backup-topology.md ----
>>"%B64%" echo ### backup-topology.md
>>"%B64%" echo LS0tCm5hbWU6IGJhY2t1cC10b3BvbG9neQpkZXNjcmlwdGlvbjogIldoZXJlIGV2ZXJ5IGJhY2t1
>>"%B64%" echo cCBsaXZlcyAoRHJpdmUsIEh5cGVyLVYgc2hhcmUsIFM6XFxNYWludF9WU0NfQkFLKSDigJQgYSBz
>>"%B64%" echo dGF0dXMgY2hlY2sgbXVzdCBjb3ZlciBhbGwgb2YgdGhlbSwgbm90IGp1c3QgdGhlIGZlZGVyYXRp
>>"%B64%" echo b24iCm1ldGFkYXRhOgogIG5vZGVfdHlwZTogbWVtb3J5CiAgdHlwZTogcHJvamVjdAotLS0KClR3
>>"%B64%" echo byBpbmRlcGVuZGVudCBiYWNrdXAgc3lzdGVtczsgYSAi0YHRgtCw0YLRg9GBINCx0Y3QutCw0L/Q
>>"%B64%" echo vtCyIiBhbnN3ZXIgbXVzdCBjb3ZlciBib3RoLgoKKipXaG8gb3ducyB3aGF0IHNpbmNlIDIwMjYt
>>"%B64%" echo MTAtMDI6KiogdGhlIGZlZGVyYXRpb24gYmFja3VwJ3MgQ09OVEVOVCAoY292ZXJhZ2UsIGV4Y2x1
>>"%B64%" echo ZGVzLAppbmJveCwgY2Fub24gwqcxNSwgRFIgZG9jcykgYmVsb25ncyB0byBhZ2VudCBgZmVkLWJh
>>"%B64%" echo Y2t1cGAgb24gc2Rldi4gVGhpcyB3aW5kb3cgb3ducyB0aGUKb3BlcmF0b3Itc2lkZSBTVE9SQUdF
>>"%B64%" echo IGJlbG93LiBSZXN0b3JlLCBzbmFwc2hvdCBkZWxldGlvbiBhbmQgcmV0ZW50aW9uIGRlcHRoIGJl
>>"%B64%" echo bG9uZyB0bwpCb3JpcyBpbiBib3RoIHN5c3RlbXMuIFNlZSBbW2ZlZGVyYXRpb24taWRlbnRpdHld
>>"%B64%" echo XS4KCjEuICoqRmVkZXJhdGlvbioqIChzbWFpbiwgYGZlZGVyYXRpb24tYmFja3VwLnNoYCwgdGlt
>>"%B64%" echo ZXIgMDI6MzUgTVNLKTogc21haW4ga2VlcHMgTk8gcmVkdW5kYW50IGNvcGllcyDigJQgb25seSAx
>>"%B64%" echo IGxvY2FsIGRhaWx5IGFzIHRoZSBgLS1saW5rLWRlc3RgIGJhc2U7IHRoZSA2ZC81dy80bSBkZXB0
>>"%B64%" echo aCBsaXZlcyBvbiBHb29nbGUgRHJpdmUgYGdkcml2ZS1tYXN0ZXI6ZmVkZXJhdGlvbi1iYWNrdXAv
>>"%B64%" echo e2RhaWx5LHdlZWtseSxtb250aGx5fWAuIFNpbmNlIDIwMjYtMDktMTMgYSBzZWNvbmQgY29weSBn
>>"%B64%" echo b2VzIHRvIGBTOlxmZWRlcmF0aW9uLWJhY2t1cGAgKG91dHNpZGUgTWFpbnRfVlNDX0JBSyDigJQg
>>"%B64%" echo cm9ib2NvcHkgL01JUiB3b3VsZCBwdXJnZSBpdCk6IHRhc2sgYEZlZGVyYXRpb25QdWxsVG9TYCAw
>>"%B64%" echo NjowMCBkYWlseSBydW5zIGBDOlxUb29sc1xyY2xvbmVccmNsb25lLmV4ZSBzeW5jIGdkcml2ZS1y
>>"%B64%" echo bzpmZWRlcmF0aW9uLWJhY2t1cCAuLi4gLS1pbmNsdWRlIC9kYWlseXx3ZWVrbHl8bW9udGhseS8q
>>"%B64%" echo KiAtLW1heC1kZWxldGUgMTBgLCBsb2cgYEM6XERldlxMb2NhbCBTbWFydGhvbWVcLmJhY2t1cC1s
>>"%B64%" echo b2dzXGZlZGVyYXRpb24tcHVsbC5sb2dgLiBSZW1vdGUgYGdkcml2ZS1yb2AgPSB0aGUgNDAwIEdC
>>"%B64%" echo IGFjY291bnQsIHNjb3BlIGRyaXZlLnJlYWRvbmx5ICh0aGUgYnJvd3NlciBvbmNlIHNpbGVudGx5
>>"%B64%" echo IGJvdW5kIGl0IHRvIHRoZSAxNSBHQiBhY2NvdW50IOKAlCB2ZXJpZnkgd2l0aCBgcmNsb25lIGFi
>>"%B64%" echo b3V0IGdkcml2ZS1ybzpgIOKGkiBUb3RhbCA0MDAgR2lCKS4gSXQgdXNlcyByY2xvbmUncyBzaGFy
>>"%B64%" echo ZWQgY2xpZW50X2lkLCByZXRpcmluZyBkdXJpbmcgMjAyNi4KMi4gKipXaW5kb3dzIHdvcmtzdGF0
>>"%B64%" echo aW9uKiogKEM6XERldiwgflwuY2xhdWRlLCBWUyBDb2RlIFVzZXI7IGBDOlxEZXZcTG9jYWwgU21h
>>"%B64%" echo cnRob21lXHNjcmlwdHNcYmFja3VwX2Rldl90b19oeXBlcnYucHMxYCwgdGFzayBgQmFja3VwRGV2
>>"%B64%" echo VG9IeXBlclZgIDIyOjAwLCBsb2dzIGluIGBDOlxEZXZcTG9jYWwgU21hcnRob21lXC5iYWNrdXAt
>>"%B64%" echo bG9nc2ApOiBwcmltYXJ5IGBcXFdpbjEwLWh5cGVydlxiYWNrdXBcRGV2YCAoPSBIOlxCQUNLVVAs
>>"%B64%" echo IFNTRDQgb24gdGhlIEh5cGVyLVYgaG9zdCksIG1pcnJvcmVkIGJ5IHJvYm9jb3B5IC9NSVIgdG8g
>>"%B64%" echo YFM6XE1haW50X1ZTQ19CQUtgIChTOiA9IGBcXFdpbjEwLWh5cGVydlxAYmFja3VwYCA9IFI6LCBT
>>"%B64%" echo ZWFnYXRlIFVTQiAyLjhUQiBvbiB0aGUgU0FNRSBob3N0KS4KCkJvcmlzIGNvdW50cyBEcml2ZSBh
>>"%B64%" echo bmQgUzpcTWFpbnRfVlNDX0JBSyBhcyB0aGUgYmFja3VwIHN0b3JlcyDigJQgSSBkaWQgbm90IGtu
>>"%B64%" echo b3cgYWJvdXQgUzogb24gMjAyNi0wOS0xMiBhbmQgZ2F2ZSB0d28gaW5jb21wbGV0ZSBzdGF0dXNl
>>"%B64%" echo cy4KCioqV2h5OioqIHN0YXR1cyByZXBvcnRzIHRoYXQgb25seSBsb29rZWQgYXQgc21haW4vRHJp
>>"%B64%" echo dmUgbWlzc2VkIGEgYnJva2VuIHdlZWtseSBhbmQgYSAyLWRheS1zdGFsZSBTOiBtaXJyb3IuCioq
>>"%B64%" echo SG93IHRvIGFwcGx5OioqIGZvciBhbnkgYmFja3VwL3Jlc3RvcmUgc3RhdHVzLCBjaGVjayBzbWFp
>>"%B64%" echo biBsb2cgKyBEcml2ZSB0aWVycyArIGRyLWRyaWxsIGRyaWxscyBBTkQgdGhlIFdpbmRvd3MgdGFz
>>"%B64%" echo ayBsb2cgKyBwcmltYXJ5IHNoYXJlICsgUzogbWlycm9yIGZyZXNobmVzcy4gQSBzdGFsZSBzdG9y
>>"%B64%" echo ZSBvbiB0aGlzIG1hY2hpbmUgaXMgaW52aXNpYmxlIHRvIHRoZSBhZ2VudCBvbiBzZGV2IOKAlCBy
>>"%B64%" echo ZXBvcnQgaXQgdG8gYGZlZC1iYWNrdXBgIHlvdXJzZWxmLCBpdCBjYW5ub3Qgc2VlIFdpbmRvd3Mu
>>"%B64%" echo Cg==

rem ---- payload: MEMORY.md ----
>>"%B64%" echo ### MEMORY.md
>>"%B64%" echo LSBbbWFpbnRlbmFuY2UtdnNjIGlkZW50aXR5XShmZWRlcmF0aW9uLWlkZW50aXR5Lm1kKSDigJQg
>>"%B64%" echo dGhpcyB3aW5kb3cgaXMgbWFpbnRlbmFuY2UtdnNjIChvcGVyYXRvci1zaWRlIGJhY2t1cCBzdG9y
>>"%B64%" echo YWdlKTsgaXQgaXMgTk8gTE9OR0VSIEZFREJBQ0tVUCwgdGhlIGZlZGVyYXRpb24gYmFja3VwIGJl
>>"%B64%" echo bG9uZ3MgdG8gYWdlbnQgZmVkLWJhY2t1cCBvbiBzZGV2IHNpbmNlIDIwMjYtMTAtMDIKLSBbTmV2
>>"%B64%" echo ZXIgcHJpbnQgc2VjcmV0IGZpbGVzXShuZXZlci1wcmludC1zZWNyZXQtZmlsZXMubWQpIOKAlCBw
>>"%B64%" echo cmludCB2YXJpYWJsZSBuYW1lcywgbmV2ZXIgdmFsdWVzOyBhIHBhcnRpYWwgbWFzayBsZWFrZWQg
>>"%B64%" echo NCBsaXZlIGtleXMKLSBbQ2xhdWRlIG9ubHkgdmlhIExpbmVtYW4gcHJveHldKGNsYXVkZS1vbmx5
>>"%B64%" echo LXZpYS1saW5lbWFuLm1kKSDigJQgQW50aHJvcGljIHRyYWZmaWMgb24gZmVkZXJhdGlvbiBub2Rl
>>"%B64%" echo cyByb3V0ZXMgdGhyb3VnaCBMaW5lbWFuLCBuZXZlciBkaXJlY3QKLSBbVlMgQ29kZTogY2xhdWRl
>>"%B64%" echo Q29kZS4qID0gc2NvcGUgbWFjaGluZV0odnNjb2RlLWJ5cGFzcy1zY29wZS1tYWNoaW5lLm1kKSDi
>>"%B64%" echo gJQg0L/QvtGH0LXQvNGDIGJ5cGFzcyDQsiAudnNjb2RlL3NldHRpbmdzLmpzb24g0L3QtSDRgNCw
>>"%B64%" echo 0LHQvtGC0LDQtdGCINC4INCz0LTQtSDQvtC9INGA0LDQsdC+0YLQsNC10YIKLSBbVlMgQ29kZSDQ
>>"%B64%" echo v9GA0L7RhNC40LvQuCDQvdCwINC/0LDQv9C60YNdKHZzY29kZS1wZXItZm9sZGVyLXByb2ZpbGVz
>>"%B64%" echo Lm1kKSDigJQgY29kZSAtLXByb2ZpbGUg0YHQvtC30LTQsNGR0YIg0L/RgNC+0YTQuNC70Ywg0LHQ
>>"%B64%" echo tdC3INGA0LDRgdGI0LjRgNC10L3QuNC5OyDRgdC60YDQuNC/0YIg0Lgg0L7QsdGF0L7QtAotIFtC
>>"%B64%" echo YWNrdXAgdG9wb2xvZ3ldKGJhY2t1cC10b3BvbG9neS5tZCkg4oCUIGZlZGVyYXRpb27ihpJEcml2
>>"%B64%" echo ZSArIHJlYWQtb25seSBwdWxsIHRvIFM6IGZlZGVyYXRpb24tYmFja3VwOyBXaW5kb3dzIERlduKG
>>"%B64%" echo kkh5cGVyLVYgc2hhcmUgbWlycm9yZWQgdG8gUzogTWFpbnRfVlNDX0JBSzsgc3RhdHVzIG11c3Qg
>>"%B64%" echo Y292ZXIgYWxsOyBjb250ZW50IG93bmVkIGJ5IGFnZW50IGZlZC1iYWNrdXAsIHN0b3JhZ2UgYnkg
>>"%B64%" echo dGhpcyB3aW5kb3cK

rem ---- unpacker ----
>>"%PY%" echo # fedbackup-role-split-v1 unpacker. Reads the base64 payload written by the .cmd,
>>"%PY%" echo # replaces the three memory cards, keeps the old ones as .bak-^<timestamp^>.
>>"%PY%" echo import base64, os, sys, time
>>"%PY%" echo.
>>"%PY%" echo memdir = os.environ.get^("MEMDIR", ""^)
>>"%PY%" echo payload = os.environ.get^("B64", ""^)
>>"%PY%" echo if not memdir or not os.path.isdir^(memdir^):
>>"%PY%" echo     sys.exit^("memory folder not found: %%r" %% memdir^)
>>"%PY%" echo if not payload or not os.path.isfile^(payload^):
>>"%PY%" echo     sys.exit^("payload not found: %%r" %% payload^)
>>"%PY%" echo.
>>"%PY%" echo items, name, buf = [], None, []
>>"%PY%" echo with open^(payload, encoding="ascii"^) as fh:
>>"%PY%" echo     for line in fh:
>>"%PY%" echo         line = line.strip^(^)
>>"%PY%" echo         if line.startswith^("### "^):
>>"%PY%" echo             if name:
>>"%PY%" echo                 items.append^(^(name, "".join^(buf^)^)^)
>>"%PY%" echo             name, buf = line[4:].strip^(^), []
>>"%PY%" echo         elif line:
>>"%PY%" echo             buf.append^(line^)
>>"%PY%" echo if name:
>>"%PY%" echo     items.append^(^(name, "".join^(buf^)^)^)
>>"%PY%" echo if len^(items^) != 3:
>>"%PY%" echo     sys.exit^("expected 3 cards in payload, got %%d" %% len^(items^)^)
>>"%PY%" echo.
>>"%PY%" echo # Decode everything BEFORE touching the disk: a broken payload must not leave the
>>"%PY%" echo # memory folder half-rewritten.
>>"%PY%" echo decoded = []
>>"%PY%" echo for n, b in items:
>>"%PY%" echo     if os.sep in n or "/" in n or n.startswith^("."^):
>>"%PY%" echo         sys.exit^("refusing suspicious name: %%r" %% n^)
>>"%PY%" echo     try:
>>"%PY%" echo         decoded.append^(^(n, base64.b64decode^(b, validate=True^)^)^)
>>"%PY%" echo     except Exception as exc:
>>"%PY%" echo         sys.exit^("bad base64 for %%s: %%s" %% ^(n, exc^)^)
>>"%PY%" echo.
>>"%PY%" echo stamp = time.strftime^("%%Y%%m%%d-%%H%%M%%S"^)
>>"%PY%" echo for n, data in decoded:
>>"%PY%" echo     path = os.path.join^(memdir, n^)
>>"%PY%" echo     if os.path.exists^(path^):
>>"%PY%" echo         os.replace^(path, path + ".bak-" + stamp^)
>>"%PY%" echo     with open^(path, "wb"^) as fh:
>>"%PY%" echo         fh.write^(data^)
>>"%PY%" echo     print^("   written", n, len^(data^), "bytes"^)
>>"%PY%" echo print^("   old cards kept with suffix .bak-" + stamp^)

python "%PY%"
if errorlevel 1 (
  echo.
  echo [FAIL] unpack step failed. Your cards were NOT replaced.
  pause
  exit /b 1
)
del "%B64%"
del "%PY%"

echo.
echo [OK] cards rewritten. This window is maintenance-vsc from now on.
echo      The federation backup belongs to agent fed-backup on sdev.
echo      The RAG sync picks the new text up within 20 minutes.
echo.
pause
