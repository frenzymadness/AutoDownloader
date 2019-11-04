#!/usr/bin/env python

# ----------------------------------------------------------------------
# Copyright (C) 2007	Robbert Gorter, Maurice van de Klundert, Mark de Vries
# Copyright (C) 2007	Hans de Goede <j.w.r.degoede@hhs.nl>
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
# ----------------------------------------------------------------------

from __future__ import print_function
import sys, string, socket, os, re, tempfile
from six.moves.urllib import request
import os
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

# overview of the settings dictionary used in class AutoDL
# key		contains
# ---------------------------------------------------------------------------
# messagelist	a list of all messages to show before beginning the download
# filelist	a list of all the files to download + name, location, md5sum, path & url's

# a messagelist:
# messagerecord = { 'title': 'example title', 'text': 'bla bla foo bar' }
# messagelist = { messagerecord1, messagerecord2, .... }

# a filelist:
#
# filelist = [ file1, file2, ..., fileN ]
# filerecord = { 'filename': 'example.tar', 'md5': '#example#', 'path': 'http://www.example.nl', 'urllist': 'an urllist') }
#
# an urllist:
# urllist = [ url1, url2, ...., urlN ]


# ----------------------------------------------------------------------
# Error and abort classes
# ----------------------------------------------------------------------


class Abort_downloader(Exception):
    pass


class Next_mirror(Exception):
    pass


class Download_stopped_by_user(Exception):
    def __init__(self):
        self.value = "Download stopped by user"

    def __str__(self):
        return repr(self.value)


class Missing_tag(Exception):
    def __init__(self, value):
        self.value = "\t" + value + " not found.\n"

    def __str__(self):
        return repr(self.value)


class Md5_error(Exception):
    pass


class Wrong_tag(Exception):
    def __init__(self, value):
        self.value = "\tWrong order" + value + " tag.\n"

    def __str__(self):
        return repr(self.value)


class Download_failed(Exception):
    def __init__(self, value):
        self.value = "\tFile " + value + " not found on server(s).\n"

    def __str__(self):
        return repr(self.value)


class Error_logger:
    def __init__(self):
        self.error_flag = False
        self.error_log = ""

    def report_error(self, error_text):
        self.error_flag = True
        self.error_log += error_text

    def flag(self):
        return self.error_flag

    def get_log(self):
        return self.error_log


# ----------------------------------------------------------------------
# Class to read the settings file, the filelist and list with mirrors
# ----------------------------------------------------------------------
class Reader:
    def read_setting(self, content, first_tag):
        offset = len(first_tag)
        last_tag = "[/" + first_tag[1:]

        find_index_start = 0
        find_index_end = 0

        find_index_start = content.find(first_tag)
        if find_index_start == -1:
            raise Missing_tag(first_tag)

        low_index = find_index_start + offset

        find_index_end = content.find(last_tag)
        if find_index_end == -1:
            raise Missing_tag(last_tag)

        high_index = find_index_end

        if find_index_start > find_index_end:
            raise Wrong_tag(first_tag)

        setting = content[low_index:high_index].strip()
        for envvar in re.findall(r"\$\w+", setting):
            setting = setting.replace(envvar, os.getenv(envvar[1:], ""))

        return setting

    def read_messagelist(self, content):

        message_list = []

        message_boundary_low = content.find("[MESSAGE]")
        if message_boundary_low == -1:
            raise Missing_tag("[MESSAGE]")

        while message_boundary_low != -1:
            message_boundary_high = content.find(
                "[/MESSAGE]", message_boundary_low
            )
            if message_boundary_high == -1:
                raise Missing_tag("[/MESSAGE]")

            valid_content = content[message_boundary_low:message_boundary_high]

            title = self.read_setting(valid_content, "[TITLE]")
            text = self.read_setting(valid_content, "[TEXT]")

            message_record = {"title": title, "text": text}
            message_list.append(message_record)
            message_boundary_low = content.find(
                "[MESSAGE]", message_boundary_high
            )

        return message_list

    def read_filelist(self, content):

        file_list = []

        file_boundary_low = content.find("[FILE]")
        if file_boundary_low == -1:
            raise Missing_tag("[FILE]")

        while file_boundary_low != -1:
            file_boundary_high = content.find("[/FILE]", file_boundary_low)
            if file_boundary_high == -1:
                raise Missing_tag("[/FILE]")

            valid_content = content[file_boundary_low:file_boundary_high]

            filename = self.read_setting(valid_content, "[FILENAME]")
            md5 = self.read_setting(valid_content, "[MD5]")
            path = self.read_setting(valid_content, "[PATH]")

            url_content = self.read_setting(valid_content, "[MIRRORS]")
            url_list = self.read_urllist(url_content)

            file_record = {
                "filename": filename,
                "md5": md5,
                "path": path,
                "urllist": url_list,
            }
            file_list.append(file_record)

            file_boundary_low = content.find("[FILE]", file_boundary_high)

        return file_list

    def read_urllist(self, content):

        url_list = []

        url_boundary_low = content.find("[URL]")
        if url_boundary_low == -1:
            raise Missing_tag("[URL]")

        while url_boundary_low != -1:
            url_boundary_low += len("[URL]")
            url_boundary_high = content.find("[/URL]", url_boundary_low)
            if url_boundary_high == -1:
                raise Missing_tag("[/URL]")

            url_list.append(
                content[url_boundary_low:url_boundary_high].strip()
            )
            url_boundary_low = content.find("[URL]", url_boundary_high)

        return url_list


# ----------------------------------------------------------------------
# Class that downloads the file(s) in the filelist
# ----------------------------------------------------------------------
class Downloader:
    def __init__(self, caller):
        self.caller = caller
        self.abort_download = False
        self.next_mirror = False
        self.mirror_count = 0
        self.mirror_total = 0
        socket.setdefaulttimeout(20)

    def stop_downloader(self):
        self.abort_download = True

    def switch_mirror(self):
        if self.mirror_count + 1 < self.mirror_total:
            self.next_mirror = True
        else:
            self.caller.report_no_next_mirror()

    def progress(self, blocks, blocksize, filesize):
        if self.abort_download:
            raise Abort_downloader

        if self.next_mirror:
            self.next_mirror = False
            raise Next_mirror

        bytes = blocks * blocksize
        if (filesize > 0) and (bytes >= filesize):
            return
        self.caller.report_progress(bytes, filesize)

    def md5_check(self, filename, md5):
        (fd, fname) = tempfile.mkstemp()
        fs = os.fdopen(fd, "w")
        fs.write(md5 + "  " + filename)
        fs.close()

        check_result = os.system(
            "md5sum --status -c " + fname + " 2> /dev/null"
        )
        os.remove(fname)

        if check_result == 0:
            return True
        else:
            return False

    def download(self, filelist):
        self.remaining_files = filelist
        for x in filelist:
            download_complete = False

            if self.md5_check(x["path"] + "/" + x["filename"], x["md5"]):
                self.remaining_files = self.remaining_files[1:]
                download_complete = True

            self.mirror_count = 0
            self.mirror_total = len(x["urllist"])
            while (
                not download_complete and self.mirror_count < self.mirror_total
            ):
                self.caller.report_file_info(
                    x["filename"],
                    x["urllist"][self.mirror_count],
                    self.mirror_count + 1,
                    self.mirror_total,
                )
                self.caller.refresh()
                if not os.path.exists(x["path"]):
                    os.makedirs(x["path"])
                try:
                    request.urlretrieve(
                        x["urllist"][self.mirror_count],
                        x["path"] + "/" + x["filename"],
                        self.progress,
                    )
                except IOError:
                    self.caller.report_broken_link(
                        x["urllist"][self.mirror_count]
                    )
                    self.mirror_count += 1
                except Abort_downloader:
                    raise Download_stopped_by_user()
                except Next_mirror:
                    self.mirror_count += 1
                except socket.timeout:
                    self.caller.report_broken_link(
                        x["urllist"][self.mirror_count]
                    )
                    self.mirror_count += 1
                except:
                    self.abort_download = True
                    raise
                else:
                    if self.md5_check(
                        x["path"] + "/" + x["filename"], x["md5"]
                    ):
                        self.remaining_files = self.remaining_files[1:]
                        download_complete = True
                    else:
                        raise Md5_error()

            if not download_complete:
                raise Download_failed(x["filename"])


# ----------------------------------------------------------------------
# GUI class
# ----------------------------------------------------------------------
class AutoDL(object):
    def __init__(self, settings, error_logger):

        """ """
        self.error_logger = error_logger
        self.settings = settings

        self.init()

    def init(self):
        filename = "/usr/share/autodl/autodl.ui"

        if not os.path.isfile(filename):
            filename = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "autodl.ui"
            )

        self.builder = Gtk.Builder()
        self.builder.add_from_file(filename)

        widget_list = [
            "AcceptWindow",
            "button_accept_no",
            "button_accept_yes",
            "message_textview",
            "DownloadWindow",
            "progressbar1",
            "label13",
            "label_filename",
            "label_filecount",
            "Md5Window",
            "button_md5_yes",
            "button_md5_no",
            "SuccessWindow",
            "button_success_yes",
            "button_success_no",
            "ErrorWindow",
            "button_exit",
            "textview3",
            "misc_download_label",
            "current_download_label",
            "mirror_label",
            "message_title_label",
        ]

        self.widgets = {}
        for w in widget_list:
            self.widgets[w] = self.builder.get_object(w)

        handlers = [
            "on_button_accept_yes_clicked",
            "on_button_md5_yes_clicked",
            "on_button_success_yes_clicked",
            "on_button_success_no_clicked",
            "on_button_download_cancel_clicked",
            "on_button_download_next_mirror_clicked",
            "on_unclean_exit_event",
        ]

        self.cb_dict = {}
        for f in handlers:
            self.cb_dict[f] = getattr(self, f)
        self.builder.connect_signals(self.cb_dict)

        textbuffer = Gtk.TextBuffer()
        iter = textbuffer.get_start_iter()

        if self.error_logger.flag():
            self.top_window = self.builder.get_object("ErrorWindow")

            textbuffer.insert(iter, self.error_logger.get_log())

            self.widgets["textview3"].set_buffer(textbuffer)
        else:
            self.top_window = self.builder.get_object("AcceptWindow")

            textbuffer.insert(iter, self.settings["messagelist"][0]["text"])

            self.widgets["message_textview"].set_buffer(textbuffer)
            self.widgets["message_title_label"].set_text(
                self.settings["messagelist"][0]["title"]
            )

            self.widgets["AcceptWindow"].show()

    def on_unclean_exit_event(self, *args):
        # remove the file we were currently downloading
        try:
            os.remove(
                self.downloader.remaining_files[0]["path"]
                + "/"
                + self.downloader.remaining_files[0]["filename"]
            )
        except:
            pass
        sys.exit(1)

    def refresh(self):
        while Gtk.events_pending():
            Gtk.main_iteration()

    def show(self):

        """
		display the top_window widget
		"""

        self.top_window.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.top_window.show()

    def set_top_window(self, top_window):

        """set_top_window(self, top_window):

		notebook pages that are in containers need to be able to change
		their top window, especially so the dialog is set_transient_for
		the actual main window
		"""

        self.top_window = top_window

    def on_button_download_cancel_clicked(self, *args):
        self.downloader.stop_downloader()

    def on_button_download_next_mirror_clicked(self, *args):
        self.downloader.switch_mirror()

    def report_progress(self, bytes, filesize):

        text_downloaded = "%s" % int(bytes / 1024)
        if filesize > 0:
            percentage = (100.0 * bytes) / filesize
            text_percent = "%s" % int(percentage)
            text_filesize = "%s" % int(filesize / 1024)

            self.widgets["progressbar1"].set_text(text_percent + " %")
            self.widgets["progressbar1"].set_fraction(percentage / 100)
            self.widgets["label13"].set_text(
                text_downloaded + " Kb / " + text_filesize + " Kb"
            )
            if percentage >= 99.5:
                self.widgets["progressbar1"].set_fraction(1)
                self.widgets["progressbar1"].set_text("100 %")
                self.widgets["label13"].set_text(
                    text_filesize + " Kb / " + text_filesize + " Kb"
                )
        else:
            self.widgets["progressbar1"].set_text("Unknown file size")
            self.widgets["label13"].set_text(text_downloaded + " Kb / Unkown")
            self.widgets["progressbar1"].pulse()

        self.refresh()

    def report_no_next_mirror(self):
        self.widgets["misc_download_label"].set_text(
            "No next mirror available, press 'Stop download' to quit now and retry later."
        )
        self.refresh()

    def report_broken_link(self, url):

        self.widgets["misc_download_label"].set_text(
            "The link " + url + " appears to be broken. Trying next mirror."
        )
        self.refresh()

    def report_file_info(self, filename, url, mirror_count, mirror_total):
        text_count = "%s" % int(mirror_count)
        text_total = "%s" % int(mirror_total)

        self.widgets["current_download_label"].set_text(
            "Filename: " + filename + "\nLocation: " + url
        )
        self.widgets["misc_download_label"].set_text("")
        self.widgets["mirror_label"].set_text(
            "Mirror " + text_count + " / " + text_total
        )

        self.refresh()

    def on_button_accept_yes_clicked(self, *args):
        self.settings["messagelist"] = self.settings["messagelist"][1:]
        if len(self.settings["messagelist"]):
            textbuffer = Gtk.TextBuffer()
            iter = textbuffer.get_start_iter()
            textbuffer.insert(iter, self.settings["messagelist"][0]["text"])
            self.widgets["message_textview"].set_buffer(textbuffer)
            self.widgets["message_title_label"].set_text(
                self.settings["messagelist"][0]["title"]
            )
            return

        self.set_top_window(self.widgets["DownloadWindow"])
        self.show()
        self.widgets["AcceptWindow"].hide()
        self.widgets["Md5Window"].hide()

        self.downloader = Downloader(self)
        try:
            self.downloader.download(self.settings["filelist"])
        except Download_failed as inst:
            self.set_top_window(self.widgets["ErrorWindow"])
            self.show()

            textbuffer = Gtk.TextBuffer()
            iter = textbuffer.get_start_iter()

            textbuffer.insert(iter, inst.value)

            self.widgets["textview3"].set_buffer(textbuffer)
        except Download_stopped_by_user as inst:
            self.set_top_window(self.widgets["ErrorWindow"])
            self.show()

            textbuffer = Gtk.TextBuffer()
            iter = textbuffer.get_start_iter()

            textbuffer.insert(iter, inst.value)

            self.widgets["textview3"].set_buffer(textbuffer)
        except Md5_error:
            self.set_top_window(self.widgets["Md5Window"])
            self.show()

        except:
            self.set_top_window(self.widgets["ErrorWindow"])
            self.show()

            textbuffer = Gtk.TextBuffer()
            iter = textbuffer.get_start_iter()

            textbuffer.insert(iter, "Unexpected error while downloading")

            self.widgets["textview3"].set_buffer(textbuffer)
            raise
        else:
            if (
                "ask_to_start" in self.settings
                and self.settings["ask_to_start"] == "FALSE"
            ):
                Gtk.main_quit()
            else:
                self.set_top_window(self.widgets["SuccessWindow"])
                self.widgets["DownloadWindow"].hide()
                self.show()

    def on_button_success_no_clicked(self, *args):
        sys.exit(2)

    def on_button_md5_yes_clicked(self, *args):
        self.settings["filelist"] = self.downloader.remaining_files
        self.on_button_accept_yes_clicked(args)

    def on_button_success_yes_clicked(self, *args):
        Gtk.main_quit()


# ----------------------------------------------------------------------
# Class to initialise the program
# ----------------------------------------------------------------------
def initialise_program(error_logger, ini_file):

    reader = Reader()
    settings = {}
    try:
        f = open(ini_file, "r")
        content = f.read()

        settings["messagelist"] = reader.read_messagelist(content)
        settings["filelist"] = reader.read_filelist(content)
        try:
            settings["ask_to_start"] = ask_to_start = reader.read_setting(
                content, "[ASK_TO_START]"
            )
        except:
            pass
    except IOError:
        error_logger.report_error("Error: " + ini_file + " does not exist.\n")
    except (Missing_tag, Wrong_tag) as inst:
        error_logger.report_error(inst.value)
    except:
        error_logger.report_error("Unexpected error.\n")
        raise
    return settings


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main(argv):
    if len(argv) != 2:
        print("Usage: " + argv[0] + " <autodl-configuration-file>")
        exit(1)

    error_logger = Error_logger()
    settings = initialise_program(error_logger, argv[1])

    w = AutoDL(settings, error_logger)
    w.show()
    Gtk.main()


if __name__ == "__main__":
    main(sys.argv)
