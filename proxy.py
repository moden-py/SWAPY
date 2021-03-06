# GUI object/properties browser.
# Copyright (C) 2016 Matiychuk D.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public License
# as published by the Free Software Foundation; either version 2.1
# of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the
#    Free Software Foundation, Inc.,
#    59 Temple Place,
#    Suite 330,
#    Boston, MA 02111-1307 USA

"""proxy module for pywinauto."""

from abc import ABCMeta, abstractproperty, abstractmethod
import exceptions
import os
import platform
import string
import thread
import time
import warnings

import pywinauto

from code_manager import CodeGenerator, check_valid_identifier
from const import *


pywinauto.timings.Timings.window_find_timeout = 1


class MetaWrapper(ABCMeta):
    """Meta class with storing list of target subclasses."""

    wrappers = {}  # List of the registered wrappers

    def __init__(cls, name, bases, attrs):
        """Register the wrapper."""
        if object not in bases \
                and 'target_class' in attrs \
                and attrs['target_class'] is not None:
            cls.wrappers[attrs['target_class']] = cls

        super(MetaWrapper, cls).__init__(name, bases, attrs)


class SWAPYWrapper(object):
    """Base proxy class(interface) for pywinauto objects."""

    __metaclass__ = MetaWrapper

    def __new__(cls, *args, **kwargs):
        """Wrap with registered wrappers."""
        if cls is SWAPYWrapper:
            # Direct call, wrap target class
            try:
                wrap_class = cls.__metaclass__.wrappers[args[0].__class__]
            except KeyError:
                # unknown class, use the default wrapper
                wrap_class = cls.__metaclass__.wrappers['default']
            instance = wrap_class(*args, **kwargs)
        else:
            # Call from a sub class
            instance = super(SWAPYWrapper, cls).__new__(cls, *args, **kwargs)
        return instance

    @property
    def _default_sort_key(self):
        """Default sort key."""
        return lambda name: name[0].lower()

    def get_properties(self):
        """Return dict of original + additional properties."""
        properties = {}
        properties.update(self._properties)
        properties.update(self._additional_properties)
        return properties

    def get_subitems(self):
        """Return list of children - [(control_text, swapy_obj),...]."""
        subitems = []

        subitems += self._children
        subitems += self._additional_children

        subitems.sort(key=self._subitems_sort_key)
        # encode names
        subitems_encoded = []
        for (name, obj) in subitems:
            # name = name.encode('cp1251', 'replace')
            subitems_encoded.append((name, obj))
        return subitems_encoded

    def execute_action(self, action):
        """Execute action on the control."""
        exec('self.pwa_obj.'+action+'()')
        return 0

    def get_actions(self):
        """Return list of the regular actions."""
        return self._actions

    def get_extended_actions(self):
        """Return list of the extended actions."""
        return self._extended_actions

    def highlight_control(self):
        """Highlight the control."""
        self._highlight_control()

    @abstractproperty
    def pwa_obj(self):
        """Pywinauto objects."""
        pass

    @abstractproperty
    def target_class(self):
        """Target wrapper's pywinauto class."""
        pass

    @abstractproperty
    def _actions(self):
        """List of the regular actions."""
        pass

    @abstractproperty
    def _additional_children(self):
        """List of the additional children."""
        pass

    @abstractproperty
    def _additional_properties(self):
        """Dict with additional actions."""
        pass

    @abstractmethod
    def _check_visibility(self):
        """Check the pywinauto object visibility."""
        pass

    @abstractproperty
    def _children(self):
        """List of the main children."""
        pass

    @abstractproperty
    def _extended_actions(self):
        """List of the extended actions."""
        pass

    @abstractmethod
    def _highlight_control(self):
        """Highlight the pywinauto object."""
        pass

    @abstractproperty
    def _properties(self):
        """Dict with regular actions."""
        pass

    @abstractproperty
    def _subitems_sort_key(self):
        """Sub items sort key."""
        pass


class NativeObject(SWAPYWrapper, CodeGenerator):
    """Mix SWAPYWrapper and the code generator."""

    target_class = 'default'
    code_self_pattern_attr = "{var} = {parent_var}.{access_name}"
    code_self_pattern_item = "{var} = {parent_var}[{access_name}]"
    code_action_pattern = "{var}.{action}()"
    main_parent_type = None
    short_name = 'control'
    __code_var_pattern = None  # cached value, to access even if the pwa
    # object was closed

    def __init__(self, pwa_obj, parent=None):
        """NativeObject constructor."""
        self._pwa_obj = pwa_obj  # original pywinauto object
        self.parent = parent
        super(NativeObject, self).__init__(pwa_obj, parent=None)

    @property
    def _actions(self):
        """
        Rreturn allowed actions for this object.

        [(id,action_name),...]
        """
        allowed_actions = []
        try:
            obj_actions = dir(self.pwa_obj.WrapperObject())
        except:
            obj_actions = dir(self.pwa_obj)
        for _id, action in ACTIONS.items():
            if action in obj_actions:
                allowed_actions.append((_id, action))
        allowed_actions.sort(key=lambda name: name[1].lower())
        return allowed_actions

    @property
    def _extended_actions(self):
        """
        Extended actions.

        May be redefined in sub classes.
        """
        return []

    @property
    def direct_parent(self):
        """Return direct parent."""
        return self.parent

    @property
    def code_parents(self):
        """
        Collect a list of all parents needed to access the control.

        Some parents may be excluded regarding to the
        `self.main_parent_type` parameter.
        """
        grab_all = True if not self.main_parent_type else False
        code_parents = []
        parent = self.parent
        while parent:
            if not grab_all and isinstance(parent, self.main_parent_type):
                grab_all = True

            if grab_all:
                code_parents.append(parent)
            parent = parent.parent
        return code_parents

    @property
    def _code_self(self):
        """Default _code_self."""
        access_name = self.get_properties()['Access names'][0]

        if check_valid_identifier(access_name):
            # A valid identifier
            code = self.code_self_pattern_attr.format(
                access_name=access_name, parent_var="{parent_var}",
                var="{var}")
        else:
            # Not valid, encode and use as app's item.
            if isinstance(access_name, unicode):
                access_name = "u'%s'" % access_name.encode('unicode-escape')
            elif isinstance(access_name, str):
                access_name = "'%s'" % access_name
            code = self.code_self_pattern_item.format(
                access_name=access_name, parent_var="{parent_var}",
                var="{var}")
        return code

    @property
    def _code_action(self):
        """Default _code_action."""
        code = self.code_action_pattern
        return code

    @property
    def _code_close(self):
        """Default _code_close."""
        return ""

    @property
    def code_var_pattern(self):
        """
        Compose variable prefix.

        Based on the control Class or short name of the SWAPY wrapper class.
        """
        if self.__code_var_pattern is None:
            var_prefix = self.short_name
            if 'Class' in self.get_properties():
                crtl_class = filter(lambda c: c in string.ascii_letters,
                                    self.get_properties()['Class']).lower()
                if crtl_class:
                    var_prefix = crtl_class

            self.__code_var_pattern = "{var_prefix}{id}".format(
                var_prefix=var_prefix, id="{id}")
        return self.__code_var_pattern

    def SetCodestyle(self, extended_action_id):
        """Switch a control code style regarding extended_action_id."""
        pass

    @property
    def _properties(self):
        """Get original pywinauto's object properties."""
        try:
            properties = self.pwa_obj.GetProperties()
        except exceptions.RuntimeError:
            properties = {}  # workaround
        return properties

    @property
    def _additional_properties(self):
        """
        Get additional useful properties, like a handle, process ID, etc.

        Can be overridden by derived class
        """
        additional_properties = {}

        # -----Access names
        access_names = [
            name for name, obj
            in self.__get_uniq_names(target_control=self.pwa_obj)
            ]
        if access_names:
            additional_properties.update({'Access names': access_names})
        # -----

        # -----pwa_type
        additional_properties.update({'pwa_type': str(type(self.pwa_obj))})
        # ---

        # -----handle
        try:
            additional_properties.update({'handle': str(self.pwa_obj.handle)})
        except:
            pass
        # ---
        return additional_properties

    @property
    def _children(self):
        """
        Return original pywinauto's object children & names.

        [(control_text, swapy_obj),...]
        """
        if self.pwa_obj.Parent() and isinstance(self.parent, Pwa_window):
            # Hide children of the non top level window control.
            # Expect all the children are accessible from the top level window.
            return []

        u_names = None
        children = []
        children_controls = self.pwa_obj.Children()
        for child_control in children_controls:
            try:
                texts = child_control.Texts()
            except exceptions.WindowsError:
                # texts = ['Unknown control name2!'] #workaround for
                # WindowsError: [Error 0] ...
                texts = None
            except exceptions.RuntimeError:
                # texts = ['Unknown control name3!'] #workaround for
                # RuntimeError: GetButtonInfo failed for button
                # with command id 256
                texts = None

            if texts:
                texts = filter(bool, texts)  # filter out '' and None items

            if texts:  # check again after the filtering
                title = ', '.join(texts)
            else:
                # .Texts() does not have a useful title, trying get it
                # from the uniqnames
                if u_names is None:
                    # init unames list
                    u_names = self.__get_uniq_names()

                child_uniq_name = [u_name for u_name, obj in u_names
                                   if obj.WrapperObject() == child_control]

                if child_uniq_name:
                    title = child_uniq_name[-1]
                else:
                    # uniqnames has no useful title
                    title = 'Unknown control name1!'
            children.append((title, SWAPYWrapper(child_control, self)))

        return children

    @property
    def _additional_children(self):
        """
        Get additional children, like for a menu, submenu, subtab, etc.

        Should be overridden in derived classes of non standard
        pywinauto object.
        """
        return []

    @property
    def _subitems_sort_key(self):
        """
        Sub items sorting key.

        Use default key.
        """
        return self._default_sort_key

    @property
    def pwa_obj(self):
        """Return pywinauto object."""
        return self._pwa_obj

    def _highlight_control(self):
        """Highlight the control."""
        def __highlight(repeat=1):
            while repeat > 0:
                repeat -= 1
                self.pwa_obj.DrawOutline('red', thickness=1)
                time.sleep(0.3)
                self.pwa_obj.DrawOutline(colour=0xffffff, thickness=1)
                time.sleep(0.2)

        if self._check_visibility():
            # TODO: can be a lot of threads
            thread.start_new_thread(__highlight, (3,))

    def _check_visibility(self):
        """
        Check control/window visibility.

        Return pwa.IsVisible() or False if fails
        """
        is_visible = False
        try:
            is_visible = self.pwa_obj.IsVisible()
        except:
            pass
        return is_visible

    def _check_actionable(self):
        """
        Check control/window Actionable.

        Return True or False if fails
        """
        try:
            self.pwa_obj.VerifyActionable()
        except:
            is_actionable = False
        else:
            is_actionable = True
        return is_actionable

    def _check_existence(self):
        """
        Check control/window Exists.

        Return True or False if fails
        """
        try:
            handle_ = self.pwa_obj.handle
            obj = pywinauto.application.WindowSpecification(
                    {'handle': handle_})
        except:
            is_exist = False
        else:
            is_exist = obj.Exists()
        return is_exist

    def __get_uniq_names(self, target_control=None):
        """
        Return uniq_names of the control.

        [(uniq_name, obj), ]
        If target_control specified, apply additional
        filtering for obj == target_control
        """
        # TODO: cache this method

        # TODO: do not call .Application() everywhere.
        pwa_app = pywinauto.application.Application()

        try:
            parent_obj = self.pwa_obj.TopLevelParent()
        except pywinauto.controls.HwndWrapper.InvalidWindowHandle:
            # For non visible windows
            # ...
            # InvalidWindowHandle: Handle 0x262710 is not a valid
            # window handle
            parent_obj = self.pwa_obj
        except AttributeError:
            return []

        visible_controls = [pwa_app.window_(handle=ch) for ch in
                            pywinauto.findwindows.find_windows(
                                    parent=parent_obj.handle,
                                    top_level_only=False)]

        uniq_names_obj = [
            (uniq_name, obj) for uniq_name, obj
            in pywinauto.findbestmatch.build_unique_dict(
                    visible_controls).items()
            if uniq_name != '' and
            (not target_control or obj.WrapperObject() == target_control)
            ]

        # sort by name
        return sorted(uniq_names_obj, key=lambda name_obj: len(name_obj[0]))


class VirtualNativeObject(NativeObject):
    target_class = None
    def __init__(self, parent, index):
        # TODO: maybe use super here?
        self.parent = parent
        self.index = index
        self._pwa_obj = self
        self._check_visibility = self.parent._check_visibility
        self._check_actionable = self.parent._check_actionable
        self._check_existence = self.parent._check_existence

    code_action_pattern = "{parent_var}.{action}({index})"

    @property
    def _code_self(self):

        """
        Rewrite default behavior.
        """
        return ""

    @property
    def _code_action(self):
        index = self.index
        if isinstance(index, unicode):
            index = "u'%s'" % index.encode('unicode-escape')
        elif isinstance(index, str):
            index = "'%s'" % index
        code = self.code_action_pattern.format(index=index,
                                               action="{action}",
                                               var="{var}",
                                               parent_var="{parent_var}")
        return code

    @property
    def code_var_pattern(self):
        raise Exception('Must not be used "code_var_pattern" prop for a VirtualSWAPYObject')
        
    def Select(self):
        self.parent.pwa_obj.Select(self.index)

    @property
    def _properties(self):
        return {}
    
    @property
    def _children(self):
        """No children"""
        return []

    @property
    def _additional_children(self):
        """No children"""
        return []

    def _highlight_control(self):
        pass

    
class PC_system(NativeObject):
    target_class = None
    handle = 0
    short_name = 'pc'  # hope it never be used in the code generator

    single_object = None
    inited = False

    def __new__(cls, *args, **kwargs):
        if cls.single_object is None:
            new = super(PC_system, cls).__new__(cls, *args, **kwargs)
            cls.single_object = new
            return new
        else:
            return cls.single_object

    def __init__(self, *args, **kwargs):
        if not self.inited:
            super(PC_system, self).__init__(*args, **kwargs)
            self.inited = True

    @property
    def _code_self(self):
        # code = self.code_self_pattern.format(var="{var}")
        # return code
        return "from pywinauto.application import Application"
    #
    # @property
    # def code_var_pattern(self):
    #     return "app{id}".format(id="{id}")

    @property
    def _children(self):
        '''
        returns [(window_text, swapy_obj),...]
        '''
        #windows--------------------
        windows = []
        try_count = 3
        app = pywinauto.application.Application()
        for i in range(try_count):
          try:
            handles = pywinauto.findwindows.find_windows()
          except exceptions.OverflowError: # workaround for OverflowError: array too large
            time.sleep(1)
          except exceptions.MemoryError:# workaround for MemoryError
            time.sleep(1)
          else:
            break
        else:
          #TODO: add swapy exception: Could not get windows list
          handles = []
        #we have to find taskbar in windows list
        warnings.filterwarnings("ignore", category=FutureWarning) #ignore future warning in taskbar module
        from pywinauto import taskbar
        taskbar_handle = taskbar.TaskBarHandle()
        for w_handle in handles:
            wind = app.window_(handle=w_handle)
            if w_handle == taskbar_handle:
                title = 'TaskBar'
            else:
                texts = wind.Texts()
                texts = filter(bool, texts)  # filter out '' and None items
                if not texts:
                    title = 'Window#%s' % w_handle
                else:
                    title = ', '.join(texts)
            windows.append((title, SWAPYWrapper(wind, self)))
        windows.sort(key=lambda name: name[0].lower())
        #-----------------------
        
        #smt new----------------
        #------------------------
        return windows

    @property
    def _properties(self):
        info = {'Platform': platform.platform(),
                'Processor': platform.processor(),
                'PC name': platform.node()}
        return info
        
    @property
    def _actions(self):
        '''
        No actions for PC_system
        '''
        return []

    def _highlight_control(self):
        pass
        
    def _check_visibility(self):
        return True
        
    def _check_actionable(self):
        return True
        
    def _check_existence(self):
        return True


class Process(CodeGenerator):

    """
    Virtual parent for window objects.
    It will never be shown in the object browser. Used to hold 'app' counter
    independent of 'window' counters.
    """
    processes = {}
    inited = False
    main_window = None

    def __new__(cls, parent, pid):
        if pid in cls.processes:
            return cls.processes[pid]
        else:
            new_process = super(Process, cls).__new__(cls, parent, pid)
            cls.processes[pid] = new_process
            return new_process

    def __init__(self, parent, pid):
        if not self.inited:
            self.parent = parent
            self._var_name = None

        self.inited = True

    @property
    def _code_self(self):
        return ""

    @property
    def _code_action(self):
        return ""

    @property
    def _code_close(self):
        return ""

    @property
    def code_var_pattern(self):
        return "{var_prefix}{id}".format(var_prefix='app', id="{id}")

    @property
    def code_var_name(self):
        if self._var_name is None:
            self._var_name = self.code_var_pattern.format(
                id=self.get_code_id(self.code_var_pattern))
        return self._var_name

    @property
    def code_parents(self):
        """Empty parents."""
        return []

    @property
    def direct_parent(self):
        """Null direct parent"""
        return None


class Pwa_window(NativeObject):
    target_class = pywinauto.application.WindowSpecification
    code_self_close = "{parent_var}.Kill_()"
    short_name = 'window'

    handles = {}
    inited = False

    def __new__(cls, pwa_obj, parent=None):
        if pwa_obj.handle in cls.handles:
            return cls.handles[pwa_obj.handle]
        else:
            new_window = super(Pwa_window, cls).__new__(cls, pwa_obj,
                                                        parent=None)
            cls.handles[pwa_obj.handle] = new_window
            return new_window

    def __init__(self, *args, **kwargs):

        process = Process(args[1], args[0].ProcessID())
        args = (args[0], process)
        if not self.inited:
            # Set default style
            self.code_self_style = self.__code_self_start
            self.code_close_style = self.__code_close_start
            super(Pwa_window, self).__init__(*args, **kwargs)

        self.inited = True

    def __code_self_connect(self):
        title = self.pwa_obj.WindowText().encode('unicode-escape')
        cls_name = self.pwa_obj.Class()
        code = "\n{parent_var} = Application().Connect(title=u'{title}', " \
               "class_name='{cls_name}')\n".format(title=title,
                                                   cls_name=cls_name,
                                                   parent_var="{parent_var}")
        return code

    def __code_self_start(self):
        target_pid = self.pwa_obj.ProcessID()
        cmd_line = None
        process_modules = pywinauto.application._process_get_modules_wmi()
        for pid, name, process_cmdline in process_modules:
            if pid == target_pid:
                cmd_line = os.path.normpath(process_cmdline)
                cmd_line = cmd_line.encode('unicode-escape')
                break
        code = "\n{parent_var} = Application().Start(cmd_line=u'{cmd_line}')\n"\
            .format(cmd_line=cmd_line, parent_var="{parent_var}")
        return code

    def __code_close_connect(self):
        return ""

    def __code_close_start(self):
        return self.code_self_close.format(parent_var="{parent_var}")

    @property
    def _code_self(self):
        code = ""
        if not self._additional_properties['Access names']:
            raise NotImplementedError
        else:
            is_main_window = bool(self.parent.main_window is None or
                                  self.parent.main_window == self or
                                  self.parent.main_window.code_var_name is None)

            if is_main_window:
                code += self.code_self_style()
                self.parent.main_window = self
            code += super(Pwa_window, self)._code_self
            if is_main_window and \
                    self.code_self_style == self.__code_self_start:
                code += "\n{var}.Wait('ready')"
                self.parent.main_window = self

        return code

    @property
    def _code_close(self):

        """
        Rewrite default behavior.
        """
        code = ""
        is_main_window = bool(self.parent.main_window is None or
                                  self.parent.main_window == self or
                                  self.parent.main_window.code_var_name is None)
        if is_main_window:
            code = self.code_close_style()

        return code

    @property
    def _additional_children(self):
        '''
        Add menu object as children
        '''
        additional_children = []
        menu = self.pwa_obj.Menu()
        if menu:
            menu_child = [('!Menu', SWAPYWrapper(menu, self))]
            additional_children += menu_child
        return additional_children

    @property
    def _additional_properties(self):
        '''
        Get additional useful properties, like a handle, process ID, etc.
        Can be overridden by derived class
        '''
        additional_properties = {}
        pwa_app = pywinauto.application.Application()
        #-----Access names

        access_names = [name for name in pywinauto.findbestmatch.build_unique_dict([self.pwa_obj]).keys() if name != '']
        access_names.sort(key=len)
        additional_properties.update({'Access names': access_names})
        #-----

        #-----pwa_type
        additional_properties.update({'pwa_type': str(type(self.pwa_obj))})
        #---

        #-----handle
        try:
            additional_properties.update({'handle': str(self.pwa_obj.handle)})
        except:
            pass
        #---
        return additional_properties

    @property
    def _extended_actions(self):

        """
        Extended actions
        """

        return [(_id, action) for _id, action in EXTENDED_ACTIONS.items()]

    def SetCodestyle(self, extended_action_id):

        """
        Switch to `Start` or `Connect` code
        """

        if 'Application.Start' == EXTENDED_ACTIONS[extended_action_id]:
            self.code_self_style = self.__code_self_start
            self.code_close_style = self.__code_close_start

        elif 'Application.Connect' == EXTENDED_ACTIONS[extended_action_id]:
            self.code_self_style = self.__code_self_connect
            self.code_close_style = self.__code_close_connect

        else:
            raise RuntimeError("Unknown menu id - %s" % extended_action_id)

        # if self.code_snippet is not None:
        #     # Refresh self code after the changing of the code style
        #     own_code_self = self.get_code_self()
        #     own_close_code = self.get_code_close()
        #     self.code_snippet.update(init_code=own_code_self,
        #                              close_code=own_close_code)

        self.update_code_style()

    def release_variable(self):
        super(Pwa_window, self).release_variable()
        if self.parent._var_name:
            self.parent._var_name = None
            self.parent.decrement_code_id(self.parent.code_var_pattern)


class Pwa_menu(NativeObject):
    target_class = pywinauto.controls.menuwrapper.Menu
    short_name = 'menu'

    def _check_visibility(self):
        is_visible = False
        try:
            is_visible = self.pwa_obj.ctrl.IsVisible()
        except AttributeError:
            pass
        return is_visible
        
    def _check_actionable(self):
        if self.pwa_obj.accessible:
            return True
        else:
            return False
        
    def _check_existence(self):
        try:
            self.pwa_obj.ctrl.handle
        except:
            return False
        else:
            return True

    @property
    def _subitems_sort_key(self):
        def key(obj):
            if hasattr(obj[1].pwa_obj, 'Index'):
                #sorts items by indexes
                return obj[1].pwa_obj.Index()
            else:
                return self._default_sort_key(obj)
        return key

    @property
    def _additional_children(self):
        '''
        Add submenu object as children
        '''
        #print(dir(self.pwa_obj))
        #print(self.pwa_obj.is_main_menu)
        #print(self.pwa_obj.owner_item)

        if not self.pwa_obj.accessible:
            return []

        additional_children = []
        menu_items = self.pwa_obj.Items()
        for menu_item in menu_items:
            item_text = menu_item.Text()
            if not item_text:
                if menu_item.Type() == 2048:
                    item_text = '-----Separator-----'
                else:
                    item_text = 'Index: %d' % menu_item.Index()
            menu_item_child = [(item_text, SWAPYWrapper(menu_item, self))]
            additional_children += menu_item_child
        return additional_children

    @property
    def _children(self):
        '''
        Return original pywinauto's object children
        
        '''
        return []

    def _highlight_control(self):
        pass


class Pwa_menu_item(Pwa_menu):
    target_class = pywinauto.controls.menuwrapper.MenuItem
    short_name = 'menu_item'

    main_parent_type = Pwa_window
    code_self_pattern = "{var} = {main_parent_var}.MenuItem(u'{menu_path}')"

    @property
    def _code_self(self):
        menu_path = self.get_menuitems_path().encode('unicode-escape')
        code = self.code_self_pattern.format(
            menu_path=menu_path, main_parent_var="{main_parent_var}",
            var="{var}")
        return code

    def _check_actionable(self):
        if self.pwa_obj.State() == 3: #grayed
            is_actionable = False
        else:
            is_actionable = True
        return is_actionable

    @property
    def _additional_children(self):
        '''
        Add submenu object as children
        '''
        #print(dir(self.pwa_obj))
        #print(self.pwa_obj.menu)
        #print self.get_menuitems_path()
        
        additional_children = []
        submenu = self.pwa_obj.SubMenu()
        if submenu:
            submenu_child = [(self.pwa_obj.Text()+' submenu', SWAPYWrapper(submenu, self))]
            additional_children += submenu_child
        return additional_children

    def get_menuitems_path(self):
        '''
        Compose menuitems_path for GetMenuPath. Example "#0 -> Save As", "Tools -> #0 -> Configure"
        '''
        path = []
        owner_item = self.pwa_obj
        
        while owner_item:
            text = owner_item.Text()
            if not text:
                text = '#%d' % owner_item.Index()
            path.append(text)
            menu = owner_item.menu
            owner_item = menu.owner_item
        return '->'.join(path[::-1])


class Pwa_combobox(NativeObject):
    target_class = pywinauto.controls.win32_controls.ComboBoxWrapper
    short_name = 'combobox'

    @property
    def _additional_children(self):
        '''
        Add ComboBox items as children
        '''
        additional_children = []
        for i, text in enumerate(self.pwa_obj.ItemTexts()):
            if not text:
                text = "option #%s" % i
                additional_children.append((text,
                                            virtual_combobox_item(self, i)))
            else:
                additional_children.append((text,
                                            virtual_combobox_item(self, text)))
        return additional_children


class virtual_combobox_item(VirtualNativeObject):

    @property
    def _properties(self):
        index = None
        text = self.index
        for i, name in enumerate(self.parent.pwa_obj.ItemTexts()):
            if name == text:
                index = i
                break
        return {'Index': index, 'Text': text}


class Pwa_listbox(NativeObject):
    target_class = pywinauto.controls.win32_controls.ListBoxWrapper
    short_name = 'listbox'

    @property
    def _additional_children(self):

        """
        Add ListBox items as children
        """

        additional_children = []
        for i, text in enumerate(self.pwa_obj.ItemTexts()):
            if not text:
                text = "option #%s" % i
                additional_children.append((text,
                                            virtual_listbox_item(self, i)))
            else:
                additional_children.append((text,
                                            virtual_listbox_item(self, text)))
        return additional_children


class virtual_listbox_item(VirtualNativeObject):

    @property
    def _properties(self):
        index = None
        text = self.index
        for i, name in enumerate(self.parent.pwa_obj.ItemTexts()):
            if name == text:
                index = i
                break
        return {'Index': index, 'Text': text}


class Pwa_listview(NativeObject):
    target_class = pywinauto.controls.common_controls.ListViewWrapper
    short_name = 'listview'

    @property
    def _additional_children(self):
        '''
        Add SysListView32 items as children
        '''
        additional_children = []
        for item in self.pwa_obj.Items():
            text = item.Text()
            if not text:
                index = item.item_index
                column_index = item.subitem_index
                text = "option #%s,%s" % (index, column_index)
            additional_children += [(text, listview_item(item, self))]
        return additional_children


class listview_item(NativeObject):
    target_class = pywinauto.controls.common_controls._listview_item
    code_self_patt_text = "{var} = {parent_var}.GetItem({text})"
    code_self_patt_index = "{var} = {parent_var}.GetItem({index}, {col_index})"
    short_name = 'listview_item'

    @property
    def _code_self(self):
        text = self.pwa_obj.Text()
        if not text:
            index = self.pwa_obj.item_index
            col_index = self.pwa_obj.subitem_index
            code = self.code_self_patt_index.format(index=index,
                                                    col_index=col_index,
                                                    parent_var="{parent_var}",
                                                    var="{var}")
        else:
            if isinstance(text, unicode):
                text = "u'%s'" % text.encode('unicode-escape')
            elif isinstance(text, str):
                text = "'%s'" % text
            code = self.code_self_patt_text.format(text=text,
                                                   parent_var="{parent_var}",
                                                   var="{var}")
        return code

    @property
    def _properties(self):
        item_properties = {'index': self.pwa_obj.item_index,
                           'column_index': self.pwa_obj.subitem_index}
        item_properties.update(self.pwa_obj.ItemData())
        return item_properties

    def _check_visibility(self):
        return True

    def _check_actionable(self):
        return True

    def _check_existence(self):
        return True

    @property
    def _children(self):
        """No children"""
        return []

    @property
    def _additional_children(self):
        """No children"""
        return []

    def _highlight_control(self):
        pass


class Pwa_tab(NativeObject):
    target_class = pywinauto.controls.common_controls.TabControlWrapper
    short_name = 'tab'

    @property
    def _additional_children(self):

        """
        Add TabControl items as children
        """

        additional_children = []
        for index in range(self.pwa_obj.TabCount()):
            text = self.pwa_obj.GetTabText(index)
            if not text:
                text = "tab #%s" % index
            additional_children += [(text, virtual_tab_item(self, index))]
        return additional_children


class virtual_tab_item(VirtualNativeObject):

    @property
    def _code_action(self):
        index = self.parent.pwa_obj.GetTabText(self.index)
        if isinstance(index, unicode):
            index = "u'%s'" % index.encode('unicode-escape')
        code = self.code_action_pattern.format(index=index,
                                               action="{action}",
                                               var="{var}",
                                               parent_var="{parent_var}")
        return code

    @property
    def _properties(self):
        item_properties = {'Index' : self.index,
                           'Texts': self.parent.pwa_obj.GetTabText(self.index)}
        return item_properties


class Pwa_toolbar(NativeObject):
    target_class = pywinauto.controls.common_controls.ToolbarWrapper
    short_name = 'toolbar'

    @property
    def _additional_children(self):
        '''
        Add button objects as children
        '''
        additional_children = []
        buttons_count = self.pwa_obj.ButtonCount()
        for button_index in range(buttons_count):
            try:
                button = self.pwa_obj.Button(button_index)
                button_text = button.info.text
                if not button_text:
                    button_text = "button #%s" % button_index
                button_object = SWAPYWrapper(button, self)
            except exceptions.RuntimeError:
                #button_text = ['Unknown button name1!'] #workaround for RuntimeError: GetButtonInfo failed for button with index 0
                pass #ignore the button
            else:
                button_item = [(button_text, button_object)]
                additional_children += button_item
        return additional_children

    @property
    def _children(self):
        '''
        Return original pywinauto's object children
        
        '''
        return []


class Pwa_toolbar_button(NativeObject):
    target_class = pywinauto.controls.common_controls._toolbar_button
    code_self_pattern = "{var} = {parent_var}.Button({index})"
    short_name = 'toolbar_button'

    @property
    def _code_self(self):
        text = self.pwa_obj.info.text
        if not text:
            index = self.pwa_obj.index
        else:
            index = text

        if isinstance(index, unicode):
            index = "u'%s'" % index.encode('unicode-escape')
        elif isinstance(index, str):
            index = "'%s'" % index

        code = self.code_self_pattern.format(index=index,
                                             action="{action}",
                                             var="{var}",
                                             parent_var="{parent_var}")
        return code

    def _check_visibility(self):
        is_visible = False
        try:
            is_visible = self.pwa_obj.toolbar_ctrl.IsVisible()
        except:
            pass
        return is_visible
        
    def _check_actionable(self):
        try:
            self.pwa_obj.toolbar_ctrl.VerifyActionable()
        except:
            is_actionable = False
        else:
            is_actionable = True
        return is_actionable
        
    def _check_existence(self):
        try:
            handle_ = self.pwa_obj.toolbar_ctrl.handle
            obj = pywinauto.application.WindowSpecification({'handle': handle_})
        except:
            is_exist = False
        else:
            is_exist = obj.Exists()
        return is_exist

    @property
    def _children(self):
        return []

    @property
    def _properties(self):
        o = self.pwa_obj
        props = {'IsCheckable': o.IsCheckable(),
                 'IsChecked': o.IsChecked(),
                 'IsEnabled': o.IsEnabled(),
                 'IsPressable': o.IsPressable(),
                 'IsPressed': o.IsPressed(),
                 'Rectangle': o.Rectangle(),
                 'State': o.State(),
                 'Style': o.Style(),
                 'index': o.index,
                 'text': o.info.text}
        return props

    def _highlight_control(self):
        pass

        
class Pwa_tree(NativeObject):
    target_class = pywinauto.controls.common_controls.TreeViewWrapper
    short_name = 'tree'

    @property
    def _additional_children(self):
        '''
        Add roots object as children
        '''
        
        additional_children = []
        roots = self.pwa_obj.Roots()
        for root in roots:
            root_text = root.Text()
            obj = SWAPYWrapper(root, self)
            obj.path = [root_text]
            root_item = [(root_text, obj)]
            additional_children += root_item
        return additional_children

    def _highlight_control(self):
        pass


class Pwa_tree_item(NativeObject):
    target_class = pywinauto.controls.common_controls._treeview_element
    main_parent_type = Pwa_tree
    code_self_pattern = "{var} = {main_parent_var}.GetItem({path})"
    short_name = 'tree_item'

    @property
    def _code_self(self):
        path = self.path
        for i in range(len(path)):
            if isinstance(path[i], unicode):
                path[i] = u'%s' % path[i].encode('unicode-escape')

        code = self.code_self_pattern.format(
            path=path, var="{var}", main_parent_var="{main_parent_var}")
        return code

    @property
    def _properties(self):
        o = self.pwa_obj
        props = {'Rectangle' : o.Rectangle(),
                 'State' : o.State(),
                 'Text' : o.Text(),}
        return props

    def _check_visibility(self):
        return True
        # TODO: It seems like pywinauto bug
        #return self.pwa_obj.EnsureVisible()
        
    def _check_existence(self):
        return True
        
    def _check_actionable(self):
        if self.parent.pwa_obj != self.pwa_obj.tree_ctrl:
            # the parent is also tree item
            return self.parent.pwa_obj.IsExpanded()
        else:
            return True

    @property
    def _children(self):
        return []
        
    def _highlight_control(self):
        pass

    @property
    def _additional_children(self):
        '''
        Add sub tree items object as children
        '''
        
        additional_children = []
        sub_items = self.pwa_obj.Children()
        for item in sub_items:
            item_text = item.Text()
            obj = SWAPYWrapper(item, self)
            obj.path = self.path + [item_text]
            sub_item = [(item_text, obj)]
            additional_children += sub_item
        return additional_children
