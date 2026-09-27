package kg.fleethub.driver_app.overlay
import android.app.*
import android.content.Intent
import android.os.IBinder
import kg.fleethub.driver_app.MainActivity

class OrderOverlayService: Service() {
    companion object { var instance: OrderOverlayService? = null }
    override fun onCreate() {
        super.onCreate()
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("fleet_shift", "Смена водителя", NotificationManager.IMPORTANCE_LOW))
        val pending = PendingIntent.getActivity(this,0,Intent(this,MainActivity::class.java),PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val stop = PendingIntent.getService(this,1,Intent(this,OrderOverlayService::class.java).setAction("STOP"),PendingIntent.FLAG_IMMUTABLE)
        startForeground(77,Notification.Builder(this,"fleet_shift").setSmallIcon(android.R.drawable.ic_menu_directions).setContentTitle("Fleet Hub работает").setContentText("Ожидаем новые заказы").setContentIntent(pending).setOngoing(true).addAction(Notification.Action.Builder(null,"Закончить смену",stop).build()).build())
        instance=this
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if(intent?.action=="STOP") { OverlayPreferences(this).driverMode=false; stopSelf() }
        return START_NOT_STICKY
    }
    override fun onDestroy() { instance=null; OverlayPreferences(this).driverMode=false; OverlayManager.get(this).hide(); super.onDestroy() }
    override fun onBind(intent: Intent?): IBinder? = null
}
