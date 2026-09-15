Kada Space X - local Hotspot lab portal

This separate copy preserves the source files in Desktop/kadaspace-x.
Use the router-local username and its separate Hotspot password, not the Wi-Fi password.
Purchases and system vouchers are not enabled. Successful login opens local status.

INSTALL
1. Extract kada-lab.zip on Windows. Keep the entire kada-lab folder together.
2. Keep the management computer connected to ether2.
3. In WinBox > Files, upload the entire kada-lab folder INSIDE flash.
   Required final path: flash/kada-lab/login.html. Upload images, CSS and md5.js too.
   The folder needs approximately 1.1 MB of free storage. Do not delete flash/axore.
4. Check in the WinBox terminal:
/file print without-paging where name~"flash/kada-lab"
5. Only after confirming the upload, enter Safe Mode (Ctrl+X) and run:
/ip hotspot profile set [find where name="yarotech-profile"] html-directory=flash/kada-lab html-directory-override=""
6. On Android connected to Yarotech-Lab, open http://10.40.0.1/login in a new private browser tab. No trailing period.
7. Test incorrect password rejection and then the correct local account login.
8. If successful, leave Safe Mode with Ctrl+X to keep the setting.

ROLLBACK (restores the previously reported directory settings)
/ip hotspot profile set [find where name="yarotech-profile"] html-directory=flash/axore html-directory-override=flash/axore

This changes portal files only. It does not change authentication methods, DHCP,
DNS, RADIUS, firewall rules or internet connectivity. It does not guarantee an
Android automatic captive-portal popup. Router upload and login remain to be tested.
The original package cleanup does not manage this manually uploaded folder.
