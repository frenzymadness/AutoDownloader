install:
	mkdir -p $(DESTDIR)/usr/share/autodl
	install -p -m 755 AutoDL.py $(DESTDIR)/usr/share/autodl
	mkdir -p $(DESTDIR)/usr/bin
	ln -s ../share/autodl/AutoDL.py $(DESTDIR)/usr/bin/autodl
	install -p -m 644 autodl.ui $(DESTDIR)/usr/share/autodl
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/16x16/apps
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/32x32/apps
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/64x64/apps
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/128x128/apps
	install -p -m 644 autodown-16.png \
	  $(DESTDIR)/usr/share/icons/hicolor/16x16/apps/autodl.png
	install -p -m 644 autodown-32.png \
	  $(DESTDIR)/usr/share/icons/hicolor/32x32/apps/autodl.png
	install -p -m 644 autodown-64.png \
	  $(DESTDIR)/usr/share/icons/hicolor/64x64/apps/autodl.png
	install -p -m 644 autodown-128.png \
	  $(DESTDIR)/usr/share/icons/hicolor/128x128/apps/autodl.png
