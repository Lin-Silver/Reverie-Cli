using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

public class DesktopFixture : Form {
    int clicks;
    Label counter;
    TextBox editor;
    string output;
    DataObject clipboardBackup;
    bool clipboardSaved;
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
            Label dragCount = new Label { Name="dragCount", Text="Drag completed: 0", Location=new Point(710,120), Size=new Size(230,30) };
            Controls.Add(dragCount);
            bool dragging = false; Point origin = Point.Empty; int completed = 0;
            Panel canvas = new Panel { Name="dragCanvas", AccessibleName="Verification drag canvas", Location=new Point(710,170), Size=new Size(230,220), BackColor=Color.LightSkyBlue };
            canvas.MouseDown += delegate(object sender, MouseEventArgs e) { if(e.Button == MouseButtons.Left) { dragging=true; origin=e.Location; } };
            canvas.MouseUp += delegate(object sender, MouseEventArgs e) { if(dragging && Math.Abs(e.X-origin.X)+Math.Abs(e.Y-origin.Y)>30) { completed++; dragCount.Text="Drag completed: " + completed; } dragging=false; };
            Controls.Add(canvas);
            Controls.Add(new Button { Name="duplicateIdentity", AccessibleName="Duplicate identity", Text="Identity A", Location=new Point(710,430), Size=new Size(200,35) });
            Controls.Add(new Button { Name="duplicateIdentity", AccessibleName="Duplicate identity", Text="Identity B", Location=new Point(710,480), Size=new Size(200,35) });
        }
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
