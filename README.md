# Desktop_Assistant

Python ve PyQt6 ile yazılmış, masaüstünde duran düşük kaynaklı bir asistan.

Sürüklenebilir bir ikon, konuşma balonu, sistem tepsisi ve kompakt bir panel içerir. CPU, RAM, disk ve pil okunur; Windows güç planı değiştirilebilir. `data/workspaces.json` profilleri tek tıkla uygulama, klasör ve site açar. Özlü sözler ve yerel takvim kayıtları balonda gösterilir.

## Çalıştırma

```powershell
py -3 -m pip install -r requirements.txt
py -3 main.py
```

İkonu sürükleyerek taşı. Sol tık paneli açar, sağ tık menüyü getirir. Kapatmak için tepsideki Çıkış kullanılır.
