using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

public class DesktopFixture : Form {
    [System.Runtime.InteropServices.DllImport("user32.dll")] static extern IntPtr SetActiveWindow(IntPtr window);
    int clicks;
    Label counter;
    TextBox editor;
    string output;
    DataObject clipboardBackup;
    bool clipboardSaved;
    string pointerDirectory;
    Panel pointerCanvas;
    Form cover;
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    static extern bool SetWindowPos(IntPtr h,IntPtr after,int x,int y,int width,int height,uint flags);
    [System.Runtime.InteropServices.DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [System.Runtime.InteropServices.DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
    [System.Runtime.InteropServices.DllImport("user32.dll")] static extern void keybd_event(byte key,byte scan,uint flags,UIntPtr extra);
    class CoverWindow : Form {
        protected override bool ShowWithoutActivation { get { return true; } }
        protected override CreateParams CreateParams { get { var p=base.CreateParams; p.ExStyle |= 0x08000000; return p; } }
    }
    public DesktopFixture(string destination) {
        output = destination;
        Text = "Reverie Computer Use Verification";
        Size = new Size(700, 600);
        StartPosition = FormStartPosition.CenterScreen;
        editor = new TextBox { Name="verificationEditor", AccessibleName="Verification editor", Multiline=true, Location=new Point(20,20), Size=new Size(640,90) };
        Controls.Add(editor);
        counter = new Label { Name="counter", Text="Count: 0", Location=new Point(20,125), Size=new Size(220,25) };
        Controls.Add(counter);
        Button increment = new Button { Name="increment", Text="Increment counter", Location=new Point(250,120), Size=new Size(150,35) };
        increment.Click += delegate { clicks++; counter.Text="Count: " + clicks; };
        Controls.Add(increment);
        Button save = new Button { Name="save", Text="Save verification", Location=new Point(420,120), Size=new Size(180,35) };
        save.Click += delegate { File.WriteAllText(output, editor.Text); counter.Text="Saved: " + clicks; };
        Controls.Add(save);
        Controls.Add(new CheckBox { Name="enable", Text="Enable verification", Location=new Point(20,175), Size=new Size(220,30) });
        ComboBox choice = new ComboBox { Name="choice", AccessibleName="Verification choice", Location=new Point(300,180), Size=new Size(250,30), DropDownStyle=ComboBoxStyle.DropDownList };
        choice.Items.AddRange(new object[] {"Alpha", "Beta", "Gamma"}); choice.SelectedIndex=0; Controls.Add(choice);
        TreeView tree = new TreeView { Name="tree", AccessibleName="Verification tree", Location=new Point(20,220), Size=new Size(250,100) };
        tree.Nodes.Add("Verification folder").Nodes.Add("Verification child"); Controls.Add(tree);
        Panel panel = new Panel { Name="scroll", AccessibleName="Verification scroll", Location=new Point(300,230), Size=new Size(350,280), AutoScroll=true, BorderStyle=BorderStyle.FixedSingle };
        for(int i=0;i<40;i++) panel.Controls.Add(new Button { Name="row"+i, Text="Verification row "+i, Location=new Point(5,i*35), Size=new Size(280,30) });
        Controls.Add(panel);
        Controls.Add(new Button { Text="Identical control", Location=new Point(20,350), Size=new Size(170,30) });
        Controls.Add(new Button { Text="Identical control", Location=new Point(20,390), Size=new Size(170,30) });
        Button second = new Button { Name="second", Text="Open second window", Location=new Point(20,450), Size=new Size(220,35) };
        second.Click += delegate { new Form { Text="Reverie Verification Second Window", Size=new Size(350,200) }.Show(this); };
        Controls.Add(second);
        Button backup = new Button { Name="backupClipboard", Text="Backup clipboard", Location=new Point(20,490), Size=new Size(130,30) };
        backup.Click += delegate {
            IDataObject source = Clipboard.GetDataObject();
            DataObject copy = new DataObject();
            if (source != null) foreach(string format in source.GetFormats(false)) copy.SetData(format, source.GetData(format, false));
            clipboardBackup = copy; clipboardSaved = true;
        };
        Controls.Add(backup);
        Button restore = new Button { Name="restoreClipboard", Text="Restore clipboard", Location=new Point(155,490), Size=new Size(130,30) };
        restore.Click += delegate { RestoreClipboard(); };
        Controls.Add(restore);
        if (Environment.GetEnvironmentVariable("REVERIE_EXTENDED_FIXTURE") == "1") {
            Size = new Size(1000, 760);
            var openDialog = new Button { Text="Open dismissal dialog", Location=new Point(710,25), Size=new Size(200,34) };
            openDialog.Click += delegate {
                BeginInvoke(new Action(delegate {
                    using (var dialog=new Form { Text="Reverie dismissal dialog", StartPosition=FormStartPosition.CenterParent }) {
                        var cancel=new Button { Text="Cancel", DialogResult=DialogResult.Cancel };
                        dialog.Controls.Add(cancel);
                        dialog.CancelButton=cancel;
                        var result=dialog.ShowDialog(this);
                        File.WriteAllText(output+".dialog",result.ToString());
                    }
                }));
            };
            Controls.Add(openDialog);
            var openMenu=new Button { Text="Open dismissal menu", Location=new Point(710,65), Size=new Size(200,34) };
            var menu=new ContextMenuStrip();
            menu.Items.Add("Keep this menu open");
            openMenu.Click += delegate {
                SetActiveWindow(Handle);
                openMenu.Focus();
                menu.Show(openMenu,0,openMenu.Height);
            };
            menu.Opened += delegate { File.WriteAllText(output+".menu","open"); };
            menu.Closed += delegate(object sender,ToolStripDropDownClosedEventArgs e){File.WriteAllText(output+".menu",e.CloseReason.ToString());};
            Controls.Add(openMenu);
            var nativeMenu=new ContextMenu(new[]{new MenuItem("Keep native menu open")});
            var openNativeMenu=new Button { Text="Open native menu", Location=new Point(420,215), Size=new Size(180,32) };
            nativeMenu.Popup += delegate { File.WriteAllText(output+".native-menu","open"); };
            openNativeMenu.Click += delegate { BeginInvoke(new Action(delegate {
                SetActiveWindow(Handle);
                openNativeMenu.Focus();
                nativeMenu.Show(openNativeMenu,new Point(0,openNativeMenu.Height));
                File.WriteAllText(output+".native-menu","closed");
            })); };
            Controls.Add(openNativeMenu);
            Label dragCount = new Label { Name="dragCount", Text="Drag completed: 0", Location=new Point(710,120), Size=new Size(230,30) };
            Controls.Add(dragCount);
            bool dragging = false; Point origin = Point.Empty; int completed = 0;
            Panel canvas = new Panel { Name="dragCanvas", AccessibleName="Verification drag canvas", Location=new Point(710,170), Size=new Size(230,220), BackColor=Color.LightSkyBlue };
            canvas.MouseDown += delegate(object sender, MouseEventArgs e) { if(e.Button == MouseButtons.Left) { dragging=true; origin=e.Location; } };
            canvas.MouseUp += delegate(object sender, MouseEventArgs e) { if(dragging && Math.Abs(e.X-origin.X)+Math.Abs(e.Y-origin.Y)>30) { completed++; dragCount.Text="Drag completed: " + completed; } dragging=false; };
            Controls.Add(canvas);
            pointerDirectory=Environment.GetEnvironmentVariable("REVERIE_POINTER_FIXTURE");
            if(!String.IsNullOrEmpty(pointerDirectory)){
                pointerCanvas=canvas;
                editor.KeyUp += delegate(object sender, KeyEventArgs e) {
                    if(File.Exists(output+".shortcut-down") && e.Modifiers==Keys.None &&
                       GetAsyncKeyState((int)Keys.ControlKey)>=0 && GetAsyncKeyState((int)Keys.ShiftKey)>=0 && GetAsyncKeyState((int)Keys.S)>=0)
                        File.WriteAllText(output+".shortcut-up","released");
                };
                var button=new Button {Text="Coordinate click", Location=new Point(710,540), Size=new Size(200,48),
                    FlatStyle=FlatStyle.Flat, UseVisualStyleBackColor=false, BackColor=Color.HotPink};
                button.FlatAppearance.MouseOverBackColor=button.BackColor;
                button.Click += delegate { File.AppendAllText(Path.Combine(pointerDirectory,"clicks.log"),"click\n"); };
                canvas.MouseDown += delegate(object sender,MouseEventArgs e){if(e.Button==MouseButtons.Left)File.AppendAllText(Path.Combine(pointerDirectory,"drag.log"),"down "+e.X+" "+e.Y+"\n");};
                canvas.MouseUp += delegate(object sender,MouseEventArgs e){if(e.Button==MouseButtons.Left)File.AppendAllText(Path.Combine(pointerDirectory,"drag.log"),"up "+e.X+" "+e.Y+"\n");};
                Controls.Add(button);
            }
            Controls.Add(new Button { Name="duplicateIdentity", AccessibleName="Duplicate identity", Text="Identity A", Location=new Point(710,430), Size=new Size(200,35) });
            Controls.Add(new Button { Name="duplicateIdentity", AccessibleName="Duplicate identity", Text="Identity B", Location=new Point(710,480), Size=new Size(200,35) });
        }
    }
    protected override bool ProcessCmdKey(ref Message message, Keys keys) {
        if(!String.IsNullOrEmpty(pointerDirectory) && editor.Focused) {
            if(keys==(Keys.Control|Keys.S)) {
                File.WriteAllText(output+".selection",editor.SelectedText);
                return true;
            }
            if(keys==(Keys.Control|Keys.Shift|Keys.S) && File.Exists(output+".hold-shortcut")) {
                File.WriteAllText(output+".shortcut-down","Ctrl+Shift+S");
                var end=DateTime.UtcNow.AddSeconds(12);
                while(!File.Exists(output+".resume-shortcut") && DateTime.UtcNow<end)
                    System.Threading.Thread.Sleep(10);
                return true;
            }
        }
        return base.ProcessCmdKey(ref message,keys);
    }
    protected override void WndProc(ref Message m) {
        if(m.Msg==0x8519 && !String.IsNullOrEmpty(pointerDirectory)){
            switch(m.WParam.ToInt32()){
            case 1: Left+=17; break;
            case 2:
                var rect=pointerCanvas.RectangleToScreen(pointerCanvas.ClientRectangle);
                cover=new CoverWindow {ShowInTaskbar=false,FormBorderStyle=FormBorderStyle.None,StartPosition=FormStartPosition.Manual,BackColor=Color.Brown};
                // Show the topmost occluder without activating it or changing the foreground owner.
                if(!SetWindowPos(cover.Handle,new IntPtr(-1),rect.X,rect.Y,rect.Width,rect.Height,0x0050)){m.Result=IntPtr.Zero;return;}
                break;
            case 3: if(cover!=null){cover.Close();cover=null;}break;
            case 4:
                if(GetForegroundWindow()!=Handle){m.Result=IntPtr.Zero;return;}
                keybd_event(0x1b,0,0,UIntPtr.Zero);
                try {System.Threading.Thread.Sleep(180);} finally {keybd_event(0x1b,0,2,UIntPtr.Zero);}
                break;
            case 5:
                using(var mutex=System.Threading.Mutex.OpenExisting(@"Local\ReverieDesktopOperations.v1")){
                    if(mutex.WaitOne(0)){mutex.ReleaseMutex();m.Result=IntPtr.Zero;return;}
                }
                break;
            case 6:
                if(!editor.Focused || editor.Text!="A12Z"){m.Result=IntPtr.Zero;return;}
                editor.Select(1,2);
                break;
            }
            m.Result=new IntPtr(1);return;
        }
        base.WndProc(ref m);
    }
    void RestoreClipboard() {
        if (!clipboardSaved) return;
        Clipboard.SetDataObject(clipboardBackup, true);
        clipboardSaved = false;
    }
    protected override void OnFormClosing(FormClosingEventArgs e) { RestoreClipboard(); base.OnFormClosing(e); }
    [STAThread] public static void Main(string[] args) {
        AppContext.SetSwitch("Switch.UseLegacyAccessibilityFeatures", false);
        AppContext.SetSwitch("Switch.UseLegacyAccessibilityFeatures.2", false);
        AppContext.SetSwitch("Switch.UseLegacyAccessibilityFeatures.3", false);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new DesktopFixture(args[0]));
    }
}
