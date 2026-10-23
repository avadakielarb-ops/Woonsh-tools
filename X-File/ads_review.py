"""Editable campaign rows and persistent validation report."""
import tkinter as tk
from tkinter import ttk, messagebox
from ads_validation import check, review_signature, manually_approved
from ui_helpers import clipboard_support

def show(parent, engine, hid, name):
    engine.history_load(hid)
    prog = engine.JOBS[hid]
    win = tk.Toplevel(parent)
    win.title('Проверка рекламы — ' + name)
    win.geometry('1100x720')
    notebook = ttk.Notebook(win)
    notebook.pack(fill='both', expand=True)
    edit, report = ttk.Frame(notebook), ttk.Frame(notebook)
    notebook.add(edit,text='Редактирование')
    notebook.add(report,text='Проверка')
    rows = []
    for site in prog.state['sites']:
        for campaign in site.get('camps',[]):
            rows.extend(campaign['rows'])
    tree = ttk.Treeview(edit,columns=('type','campaign','group'),show='headings')
    for key,label in [('type','Тип'),('campaign','Кампания'),('group','Группа')]:
        tree.heading(key,text=label)
    tree.pack(fill='both',expand=True)
    for i,r in enumerate(rows):
        tree.insert('', 'end',iid=str(i), values=(r.get('Row Type') or r.get('Asset type'),r.get('Campaign'),r.get('Ad group')))
    fields = ttk.Combobox(edit,state='readonly',width=50)
    fields.pack(fill='x',padx=8,pady=6)
    value = tk.Text(edit,height=4,wrap='word')
    value.pack(fill='x',padx=8)
    clipboard_support(value)
    approved = tk.BooleanVar(value=manually_approved(prog.state))
    ttk.Checkbutton(report,text='Проверил, принимаю замечания и ошибки — разрешить экспорт',variable=approved).pack(anchor='w',padx=8,pady=8)
    output = tk.Text(report,wrap='word')
    output.pack(fill='both',expand=True)
    def load_value(*args):
        value.delete('1.0','end')
        if tree.selection() and fields.get():
            value.insert('1.0', rows[int(tree.selection()[0])].get(fields.get(),''))
    def pick(*args):
        if tree.selection():
            row = rows[int(tree.selection()[0])]
            fields.configure(values=list(dict.fromkeys(list(row)+engine.CSV_COLUMNS)))
            fields.set(next(iter(row),''))
            load_value()
    tree.bind('<<TreeviewSelect>>',pick)
    fields.bind('<<ComboboxSelected>>',load_value)
    def validate():
        errors,warnings = check(rows,prog.state['s'],engine.policy_issue)
        output.configure(state='normal')
        output.delete('1.0','end')
        output.insert('1.0','Ошибки:\n'+ ('\n'.join(errors) or 'Нет')+'\n\nЗамечания:\n'+ ('\n'.join(warnings) or 'Нет'))
        output.configure(state='disabled')
        return errors
    def apply():
        if tree.selection() and fields.get():
            row = rows[int(tree.selection()[0])]
            new_value = value.get('1.0','end-1c').strip()
            if row.get(fields.get(),'') != new_value:
                approved.set(False)
                prog.state.pop('manual_review',None)
            row[fields.get()] = new_value
            validate()
    def save():
        apply()
        if approved.get():
            import datetime
            prog.state['manual_review']={'signature':review_signature(prog.state), 'at':datetime.datetime.now().astimezone().isoformat()}
        else:
            prog.state.pop('manual_review',None)
        prog.result = engine.assemble(prog.state)
        engine.save_history(hid,prog,[s['url'] for s in prog.state['sites']])
        if not prog.hist_path:
            messagebox.showerror('Сохранение','Не удалось сохранить изменения.',parent=win)
            return
        parent.run_status.pop(prog.profile.get('key','')+'\n'+prog.profile.get('site',''),None)
        import json
        temp = parent.run_path.with_suffix('.tmp')
        temp.write_text(json.dumps(parent.run_status,ensure_ascii=False),encoding='utf-8')
        temp.replace(parent.run_path)
        parent.refresh()
        notebook.select(report)
    bar=ttk.Frame(win)
    bar.pack(fill='x',padx=8,pady=8)
    ttk.Button(bar,text='Применить поле',command=apply).pack(side='left')
    ttk.Button(bar,text='Проверить',command=lambda:(validate(),notebook.select(report))).pack(side='left',padx=6)
    ttk.Button(bar,text='Сохранить изменения',command=save).pack(side='left')
    validate()
