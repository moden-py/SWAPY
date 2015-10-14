
from Tkinter import BOTH, Tk, Menu, Toplevel, Label, Entry, Button, Checkbutton
from ttk import Treeview

POPUP_MENU_ACTIONS = ('Close', 'Click', 'ClickInput', 'CloseClick', 'DoubleClick', 'DoubleClickInput', 'DragMouse',
                      'DrawOutline', 'Maximize', 'Minimize', 'MoveMouse', 'MoveWindow', 'PressMouse',
                      'PressMouseInput', 'ReleaseMouse', 'ReleaseMouseInput', 'Restore', 'RightClick',
                      'RightClickInput', 'SetFocus', 'Select', 'Collapse', 'Expand')

START_SUB_MENU_ITEMS = ("Application.Start(path='user_software.exe line params')",
                        "Custom")

CONNECT_SUB_MENU_ITEMS = ("Application.Connect(path='user_software.exe')",
                          "Application.Connect(title='Software Title')",
                          "Application.Connect(pid=5349)",
                          "Custom")

class MyDialog:

    def __init__(self, parent):

        top = self.top = Toplevel(parent)

        Label(top, text="Value").pack()

        self.e = Entry(top)
        self.e.pack(padx=5)

        b = Button(top, text="OK", command=self.ok)
        b.pack(pady=5)

    def ok(self):

        print "value is", self.e.get()

        self.top.destroy()


def window_start():

    wdw = Toplevel()
    wdw.wm_title("start")
    wdw.geometry('+400+400')

    Label(wdw, text="cmd_line").pack()
    e = Entry(wdw)
    e.pack()
    e.focus_set()
    Button(wdw, text="Browse").pack(pady=5)

    Label(wdw, text="timeout").pack()
    Entry(wdw).pack()

    Label(wdw, text="retry_interval").pack()
    Entry(wdw).pack()

    Checkbutton(wdw, text="create_new_console", variable=False).pack()

    Checkbutton(wdw, text="wait_for_idle", variable=True).pack()

    Button(wdw, text="OK", command=wdw.destroy).pack(pady=5)

    wdw.transient(root)
    wdw.grab_set()
    root.wait_window(wdw)


def window_connect():

    wdw = Toplevel()
    wdw.wm_title("Connect")
    wdw.geometry('+400+400')

    Label(wdw, text="process").pack()
    e = Entry(wdw)
    e.pack()
    e.focus_set()

    Label(wdw, text="handle").pack()
    Entry(wdw).pack()

    Label(wdw, text="path").pack()
    Entry(wdw).pack()

    Label(wdw, text="+ all findwindows kwargs").pack()

    Button(wdw, text="OK", command=wdw.destroy).pack(pady=5)

    wdw.transient(root)
    wdw.grab_set()
    root.wait_window(wdw)


def create_popup_menu(x, y, item):
    popup_menu = Menu(browser, tearoff=0)
    start_sub_menu = Menu(browser, tearoff=0)
    connect_sub_menu = Menu(browser, tearoff=0)

    popup_menu.add_cascade(label="Application.Start", menu=start_sub_menu)
    popup_menu.add_cascade(label="Application.Connect", menu=connect_sub_menu)

    if item == "I001":
        start_sub_menu.add_command(label=START_SUB_MENU_ITEMS[-1], command=window_start)
        connect_sub_menu.add_command(label=CONNECT_SUB_MENU_ITEMS[-1], command=window_connect)
    else:
        for i in START_SUB_MENU_ITEMS:
            start_sub_menu.add_command(label=i, command=window_start)

        for i in CONNECT_SUB_MENU_ITEMS:
            connect_sub_menu.add_command(label=i, command=window_connect)

        popup_menu.add_separator()
        for i in POPUP_MENU_ACTIONS:
            popup_menu.add_command(label=i)

    popup_menu.post(x, y)


def on_right_click(event):
    item = browser.identify('item', event.x, event.y)
    create_popup_menu(event.x_root, event.y_root, item)


if __name__ == "__main__":
    root = Tk()

    browser = Treeview(root, show='tree', selectmode='browse')
    browser.pack(fill=BOTH, expand=True)
    root_element = browser.insert("", "end", text='Root element', open=True)
    for i in range(3):
        browser.insert(root_element, "end", text='Window #%s' % i)

    browser.bind("<Button-3>", on_right_click)





    root.mainloop()
