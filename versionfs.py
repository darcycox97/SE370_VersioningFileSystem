#!/usr/bin/env python

from __future__ import with_statement

import logging

import os.path
import os
import sys
import errno
import shutil
import filecmp

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn

######### MODIFIED BY: Darcy Cox (dcox740) ###########

class VersionFS(LoggingMixIn, Operations):

    # fields representing the operations of a save operation (write, flush, then release)
    WRITE = "write"
    FLUSH = "flush"
    RELEASE = "release"

    # name of folder to store versions in.
    # separate folder for versions is used so we can easily exclude this folder
    # from the users view of the mount directory, so users will not be aware of versioning
    VERSIONS_FOLDER = ".versions"

    possible_save = False   # true if the sequence of operations is a subset of the save sequence
    current_state = None    # which operation was just executed, None if not part of the save sequence

    def __init__(self):
        # get current working directory as place for versions tree
        self.root = os.path.join(os.getcwd(), '.versiondir')
        # check to see if the versions directory already exists
        if os.path.exists(self.root):
            print 'Version directory already exists.'
        else:
            print 'Creating version directory.'
            os.mkdir(self.root)

    # Helpers
    # =======

    def _full_path(self, partial):
        if partial.startswith("/"):
            partial = partial[1:]
        path = os.path.join(self.root, partial)
        return path

    # finite-state-machine-esque implementation to determine when we have the
    # write -> flush -> release sequence in that exact order. when this occurs
    # we know that a save has occurred. Returns true when a save has occurred
    def _update_save_state_machine(self, operation):
        if ((operation == self.WRITE)
            or (self.current_state == self.WRITE and operation == self.FLUSH)
            or (self.current_state == self.FLUSH and operation == self.RELEASE and self.possible_save)):
            # valid transition in the state machine, could lead to a save
            self.possible_save = True
        else:
            # invalid state, sequence cannot lead to a save
            self.possible_save = False

        self.current_state = operation

        # save operation occurred if in valid state and most recent op was RELEASE
        if (self.possible_save and self.current_state == self.RELEASE):
            return True

        return False


    # returns the full pathname of the versioned file with specified version number
    def _version_path(self, full_path, version):
        dirname = os.path.dirname(full_path)
        basename = os.path.basename(full_path)
        version_path = os.path.join(dirname, self.VERSIONS_FOLDER, '.' + basename + '.ver.' + str(version))
        return version_path

    # creates a new version for the specified file and modifies the version numbers
    # of pre-existing versions of that file if necessary. 
    def _create_new_version(self, full_path):

        # create .versions folder if it doesn't exist
        if not os.path.exists(self._full_path(self.VERSIONS_FOLDER)):
            os.mkdir(self._full_path(self.VERSIONS_FOLDER)) 

            

        # if the file is already versioned, update the version numbers of the older versions
        # overwriting the 6th version if need be, as only max 6 versions should be stored
        version_1 = self._version_path(full_path, 1)
        if os.path.exists(version_1):
            print 'incrementing old versions'
            for i in range(5,0,-1):
                version_path = self._version_path(full_path, i)
                older_version_path = self._version_path(full_path, i + 1)
                if os.path.exists(version_path):
                    shutil.copy(version_path, older_version_path)

        # create the new version
        print 'creating new version'
        shutil.copy(full_path, version_1)


    # Filesystem methods
    # ==================

    def access(self, path, mode):
        # self._update_save_state_machine(None)
        # print "access:", path, mode
        full_path = self._full_path(path)
        if not os.access(full_path, mode):
            raise FuseOSError(errno.EACCES)

    def chmod(self, path, mode):
        # self._update_save_state_machine(None)
        # print "chmod:", path, mode
        full_path = self._full_path(path)
        return os.chmod(full_path, mode)

    def chown(self, path, uid, gid):
        # self._update_save_state_machine(None)
        # print "chown:", path, uid, gid
        full_path = self._full_path(path)
        return os.chown(full_path, uid, gid)

    def getattr(self, path, fh=None):
        # self._update_save_state_machine(None)
        # print "getattr:", path
        full_path = self._full_path(path)
        st = os.lstat(full_path)
        return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                     'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))

    def readdir(self, path, fh):
        # self._update_save_state_machine(None)
        # print "readdir:", path
        # TODO: filter out the version files (should be hidden in MOUNT dir)
        full_path = self._full_path(path)

        dirents = ['.', '..']
        if os.path.isdir(full_path):
            dirents.extend(os.listdir(full_path))
        for r in dirents:
            # return all contents of directory except for versions folder
            print r
            if r != self.VERSIONS_FOLDER:
                yield r

    def readlink(self, path):
        # self._update_save_state_machine(None)
        # print "readlink:", path
        pathname = os.readlink(self._full_path(path))
        if pathname.startswith("/"):
            # Path name is absolute, sanitize it.
            return os.path.relpath(pathname, self.root)
        else:
            return pathname

    def mknod(self, path, mode, dev):
        # self._update_save_state_machine(None)
        # print "mknod:", path, mode, dev
        return os.mknod(self._full_path(path), mode, dev)

    def rmdir(self, path):
        # self._update_save_state_machine(None)
        # print "rmdir:", path
        full_path = self._full_path(path)
        return os.rmdir(full_path)

    def mkdir(self, path, mode):
        # self._update_save_state_machine(None)
        # print "mkdir:", path, mode
        return os.mkdir(self._full_path(path), mode)

    def statfs(self, path):
        # self._update_save_state_machine(None)
        # print "statfs:", path
        full_path = self._full_path(path)
        stv = os.statvfs(full_path)
        return dict((key, getattr(stv, key)) for key in ('f_bavail', 'f_bfree',
            'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files', 'f_flag',
            'f_frsize', 'f_namemax'))

    def unlink(self, path):
        # self._update_save_state_machine(None)
        # print "unlink:", path
        return os.unlink(self._full_path(path))

    def symlink(self, name, target):
        # self._update_save_state_machine(None)
        # print "symlink:", name, target
        return os.symlink(target, self._full_path(name))

    def rename(self, old, new):
        # self._update_save_state_machine(None)
        # print "rename:", old, new
        return os.rename(self._full_path(old), self._full_path(new))

    def link(self, target, name):
        # self._update_save_state_machine(None)
        # print "link:", target, name
        return os.link(self._full_path(name), self._full_path(target))

    def utimens(self, path, times=None):
        # self._update_save_state_machine(None)
        # print "utimens:", path, times
        return os.utime(self._full_path(path), times)

    # File methods
    # ============

    def open(self, path, flags):
        self._update_save_state_machine(None)
        print '** open:', path, '**'
        full_path = self._full_path(path)
        return os.open(full_path, flags)

    def create(self, path, mode, fi=None):
        self._update_save_state_machine(None)
        print '** create:', path, '**'
        full_path = self._full_path(path)
        return os.open(full_path, os.O_WRONLY | os.O_CREAT, mode)

    def read(self, path, length, offset, fh):
        self._update_save_state_machine(None)
        print '** read:', path, '**'
        os.lseek(fh, offset, os.SEEK_SET)
        return os.read(fh, length)

    def write(self, path, buf, offset, fh):
        self._update_save_state_machine(self.WRITE)
        print '** write:', path, '**'
        os.lseek(fh, offset, os.SEEK_SET)
        return os.write(fh, buf)

    def truncate(self, path, length, fh=None):
        self._update_save_state_machine(None)
        print '** truncate:', path, '**'
        full_path = self._full_path(path)
        with open(full_path, 'r+') as f:
            f.truncate(length)

    def flush(self, path, fh):
        self._update_save_state_machine(self.FLUSH)
        print '** flush', path, '**'
        return os.fsync(fh)

    def release(self, path, fh):
        print '** release', path, '**'
        close_val = os.close(fh)
        # check if the sequence of operations ending in release was a save operation
        if self._update_save_state_machine(self.RELEASE):
            full_path = self._full_path(path)
            # only visible files should be versioned, so check first character of basename
            if os.path.basename(path)[:1] != '.':
                print 'save!'
                # the file is visible and and is being saved
                # compare it against the current version to see if it has been modified,
                # and if so, create a new version
                current_version = self._version_path(full_path, 1)
                if os.path.exists(current_version):
                    if not filecmp.cmp(full_path, current_version):
                        self._create_new_version(full_path)
                    else: 
                        print 'no changes from current version'
                else:
                    self._create_new_version(full_path)
        
        return close_val

    def fsync(self, path, fdatasync, fh):
        self._update_save_state_machine(None)
        print '** fsync:', path, '**'
        return self.flush(path, fh)


def main(mountpoint):
    FUSE(VersionFS(), mountpoint, nothreads=True, foreground=True)

if __name__ == '__main__':
    # logging.basicConfig(level=logging.DEBUG)
    main(sys.argv[1])