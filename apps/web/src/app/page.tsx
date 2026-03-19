import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen bg-linear-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-8">
      <div className="max-w-2xl w-full text-center space-y-6">
        <h1 className="text-4xl font-bold text-gray-800">TP AI</h1>
        <p className="text-lg text-gray-600">
          AI асистент за съставяне на Технически предложения за обществени поръчки
        </p>
        <div className="flex gap-4 justify-center">
          <Link
            href="/projects"
            className="px-6 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition"
          >
            Моите проекти
          </Link>
          <Link
            href="/projects/new"
            className="px-6 py-3 bg-white text-blue-600 border-2 border-blue-600 rounded-xl font-semibold hover:bg-blue-50 transition"
          >
            Нов проект
          </Link>
        </div>
      </div>
    </main>
  );
}
